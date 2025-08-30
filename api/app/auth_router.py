# api/app/auth_router.py
from fastapi import APIRouter, HTTPException, Request, Depends, Body
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer

from typing import List, Dict, Any

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from jose import JWTError, jwt
from passlib.context import CryptContext
from bson import ObjectId

import os
import tempfile
import pandas as pd
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from minio.error import S3Error

from api.app.database import ensure_mongo_collections, get_minio_client, ensure_bucket, minio_file_url, DATAX_MINIO_BUCKET_SHEETS
from api.app.session_manager import sessions, initialize_session
from api.app.models import SignupIn, LoginIn, VerifyIn, ForgotPasswordIn, ResetPasswordIn, ExchangeCodeIn

# =========================
# Environment & constants
# =========================
load_dotenv(".env")

client, db, chat_sessions_collection, users_collection = ensure_mongo_collections()

# For local testing only. Remove in production.
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "0"

# Google OAuth settings from environment variables
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_TOKEN_URI = os.getenv("GOOGLE_TOKEN_URI")
GOOGLE_AUTH_URI = os.getenv("GOOGLE_AUTH_URI")
GOOGLE_AUTH_PROVIDER_X509_CERT_URL = os.getenv("GOOGLE_AUTH_PROVIDER_X509_CERT_URL")
GOOGLE_PROJECT_ID = os.getenv('GOOGLE_PROJECT_ID')

# Check for the existence of variables
if not all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_TOKEN_URI, GOOGLE_AUTH_URI, GOOGLE_AUTH_PROVIDER_X509_CERT_URL,GOOGLE_PROJECT_ID]):
    raise ValueError("Missing Google OAuth environment variables")

# Client settings for Flow
client_config = {
    "web": {
        "client_id": GOOGLE_CLIENT_ID,
        "project_id": GOOGLE_PROJECT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "auth_uri": GOOGLE_AUTH_URI,
        "token_uri": GOOGLE_TOKEN_URI,
        "auth_provider_x509_cert_url": GOOGLE_AUTH_PROVIDER_X509_CERT_URL
    }
}

# Frontend callback where Google redirects after Sheets consent
FRONTEND_URL = os.getenv("FRONTEND_URL")
FRONTEND_SHEETS_CALLBACK = f"{FRONTEND_URL}/google-sheets/callback"

# JWT
SECRET_KEY = os.getenv("JWT_SECRET", "dev_secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Google scopes (Sheets connection ONLY)
SCOPES_SHEETS = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/userinfo.email"
]

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# FastAPI router / auth scheme
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# =========================
# Helpers: JWT & Passwords
# =========================
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    user_id = decode_token(token)  
#    print(f"Decoded user_id from token: {user_id}")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        user = db["users"].find_one({"_id": ObjectId(user_id)})
    except:
        raise HTTPException(status_code=401, detail="Invalid user id in token")
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# =========================
# Helper: extract email from JWT
# =========================

def get_current_email_from_session(user: Dict[str, Any] = Depends(get_current_user)) -> str:
    email = user.get("email")
#    print(f"Extracted email: {email}")
    if not email:
        raise HTTPException(status_code=400, detail="Email not found in session")
    return email

# =========================
# Auth: Email/Password
# =========================

@auth_router.post("/signup")
async def signup(payload: SignupIn):
    from api.app.agent import get_agent  # Lazy import
    existing = db["users"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    verification_code = "123456"

    user_doc = {
        "full_name": payload.full_name,
        "email": payload.email,
        "phone": payload.phone,
        "password_hash": hash_password(payload.password),
        "verification_code": verification_code,
        "is_verified": False,
        "created_at": datetime.now(timezone.utc),
        "last_login": None,
        "google_credentials": None,
    }
    result = db["users"].insert_one(user_doc)

    # ⚡ Now we put the real user_id in the token
    token = create_access_token({"sub": str(result.inserted_id)})
    session_id, sessions[session_id], saving_message = initialize_session()
    success = {
        "message": "Signup successful. Please verify your account with the code.",
        "user_id": str(result.inserted_id),
        "token": token,
        "token_type": "bearer"
    }

    print(success)  # Just logs to console
    return success

@auth_router.post("/login")
def login(payload: LoginIn):
    from api.app.agent import get_agent  # Lazy import
    # Find user by email
    user = db["users"].find_one({"email": payload.email})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # ✅ Prevent login if account is not verified
    if not user.get("is_verified", False):
        raise HTTPException(status_code=403, detail="Account not verified. Please verify your email first.")

    # Update last_login timestamp
    db["users"].update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login": datetime.now(timezone.utc)}}
    )

    # Generate JWT token and create session
    token = create_access_token({"sub": str(user["_id"])})
    session_id, sessions[session_id], saving_message = initialize_session()

    # Log data for backend debugging
    login_data = {
        "message": "Login successful",
        "token": token,
        "session_id": session_id,
        "user": {
            "id": str(user["_id"]),
            "email": user["email"],
            "name": user.get("name")
        }
    }

    success = {
    "message": "Login successful",
    "token": token,
    "session_id": session_id,
    "user": {
        "id": str(user["_id"]),
        "email": user["email"],
        "name": user.get("name")
    }
    }
    print(success)
    return success

# =========================
# /auth/verify  (Only code comes from the frontend; email from JWT)
# =========================
@auth_router.post("/verify")
def verify_user(payload: VerifyIn, email: str = Depends(get_current_email_from_session)):
    user = db["users"].find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    stored_code = user.get("verification_code")
    if payload.code != stored_code:
        raise HTTPException(status_code=400, detail="Invalid verification code")
    
    db["users"].update_one(
        {"_id": user["_id"]},
        {"$set": {
        "is_verified": True,
        "verified_at": datetime.now(timezone.utc)}})
    # Generate JWT token and create session
    token = create_access_token({"sub": str(user["_id"])})
    success = {
    "message": "Account verified successfully",
    "token": token,
    "email": user.get("email"),
    "id": str(user["_id"]),
    "created_at": user.get("created_at"),
    "is_verified": user.get("is_verified"),}

    print(success)
    return success

# =========================
# /auth/forgot-password
# =========================
@auth_router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordIn):
    user = db["users"].find_one({"email": payload.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    reset_token = create_access_token({"sub": str(user["_id"])})
    reset_link = f"{FRONTEND_URL}/reset-password?token={reset_token}"
    token = create_access_token({"sub": str(user["_id"])})
    
    success = {
        "message": "Password reset link generated successfully",
        "token":token,
        "email": user.get("email"),
        "user_id": str(user["_id"]),
        "reset_link": reset_link
    }
    
    # Log
    print(success)    
    return success


# =========================
# /auth/reset-password
# =========================
@auth_router.post("/reset-password")
def reset_password(payload: ResetPasswordIn, email: str = Depends(get_current_email_from_session)):
    user = db["users"].find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db["users"].update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password)}}
    )
    token = create_access_token({"sub": str(user["_id"])})
    success = {
        "message": "Password reset successful",
        "token": token,
        "email": email,
        "user_id": str(user["_id"])
    }
    
    # Log
    print(success)
    return success


# ==========================================
# Connect Google Sheets (redirect + callback combined)
# ==========================================
# Begin OAuth
@auth_router.get("/connect-google-sheets")
def connect_google_sheets(user=Depends(get_current_user)):
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES_SHEETS,
        redirect_uri=FRONTEND_SHEETS_CALLBACK,
    )
    auth_url, state = flow.authorization_url(prompt="consent")
    sessions[str(user["_id"])] = {"state": state}
    
    return {"auth_url": auth_url, "state": state}

# Code exchange and data storage
@auth_router.post("/google-sheets/exchange")
def exchange_code_and_ingest(payload: ExchangeCodeIn, user=Depends(get_current_user)):
    stored_state = sessions.get(str(user["_id"]), {}).get("state")
    if not stored_state:
        raise HTTPException(status_code=400, detail="Invalid state")
    print(f"code:{payload.code}")

    # Step 1: Exchange code → tokens
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES_SHEETS,
        redirect_uri=FRONTEND_SHEETS_CALLBACK,
    )
    try:
        flow.fetch_token(code=payload.code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to exchange code: {e}")
    credentials = flow.credentials

    # Step 2: Get Google account email
    oauth2_service = build("oauth2", "v2", credentials=credentials)
    try:
        user_info = oauth2_service.userinfo().get().execute()
        google_email = user_info.get("email")
        if not google_email:
            raise HTTPException(status_code=400, detail="Failed to retrieve Google email")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Failed to fetch user info: {str(e)}")

    # Step 3: Save credentials in Mongo
    creds_dict = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }
    db["users"].update_one(
        {"_id": user["_id"]},
        {"$set": {
            "google_email": google_email,
            "google_credentials": creds_dict,
            "sheets_connected_at": datetime.now(timezone.utc)
        }},
    )

    # Step 4: Ingest sheets → MinIO
    uploaded_to_minio = _ingest_user_sheets_to_minio(
        user_id=str(user["_id"]), creds=credentials
    )

    # Clear state after successful exchange
    sessions.pop(str(user["_id"]), None)
    
    return {
        "message": "Google Sheets connected and ingested successfully",
        "google_email": google_email,
        "uploaded_to_minio": uploaded_to_minio,  # list of {sheet_id, filename, url, ...}
    }


def _refresh_credentials_if_needed(creds_dict: Dict[str, Any]) -> Dict[str, Any]:
    creds = Credentials(**creds_dict)
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        # write-back refreshed creds
        refreshed = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes,
        }
        return refreshed
    return creds_dict


def _ingest_user_sheets_to_minio(user_id: str, creds: Credentials) -> List[Dict[str, Any]]:
    """
    Lists user's spreadsheets, downloads a sample (headers + first rows),
    saves CSV to MinIO, and stores metadata in MongoDB.
    """
    drive = build("drive", "v3", credentials=creds)
    sheets = drive.files().list(
        q="mimeType='application/vnd.google-apps.spreadsheet'",
        fields="files(id, name)"
    ).execute().get("files", [])

    minio_client = get_minio_client()
    ensure_bucket(minio_client, DATAX_MINIO_BUCKET_SHEETS)

    uploaded = []
    for f in sheets:
        sheet_id = f["id"]
        sheet_name = f["name"]

        # Pull first rows from the sheet
        svc = build("sheets", "v4", credentials=creds)
        values = svc.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="A1:Z50"  # a small preview/export; adjust as needed
        ).execute().get("values", [])

        if not values:
            headers = []
            df = pd.DataFrame()
        else:
            headers = values[0]
            df = pd.DataFrame(values[1:], columns=headers) if len(values) > 1 else pd.DataFrame(columns=headers)

        # Save to a temporary CSV file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            csv_path = tmp.name
        df.to_csv(csv_path, index=False, encoding="utf-8")

        # Upload to MinIO under user_id/sheet_id.csv
        object_name = f"{user_id}/{sheet_id}.csv"
        try:
            minio_client.fput_object(DATAX_MINIO_BUCKET_SHEETS, object_name, csv_path)
        except S3Error as e:
            # clean temp and continue
            try:
                os.remove(csv_path)
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=f"MinIO upload failed: {e}")

        # Remove temp file
        try:
            os.remove(csv_path)
        except Exception:
            pass

        file_url = minio_file_url(DATAX_MINIO_BUCKET_SHEETS, object_name)

        # Store/Upsert metadata for listing
        meta = {
            "owner_id": user_id,
            "sheet_id": sheet_id,
            "sheet_name": sheet_name,
            "bucket": DATAX_MINIO_BUCKET_SHEETS,
            "object_name": object_name,
            "file_url": file_url,
            "headers": headers,
            "rows_saved": int(df.shape[0]),
            "columns": int(df.shape[1]),
            "updated_at": datetime.now(timezone.utc),
        }
        db["spreadsheet_metadata"].update_one(
            {"owner_id": user_id, "sheet_id": sheet_id},
            {"$set": meta},
            upsert=True,
        )
        uploaded.append(meta)

    return uploaded


# ==========================================
# List ingested sheets for current user
# ==========================================
# ==========================================
# List ingested sheets for current user
# ==========================================
@auth_router.get("/sheets")
def list_my_sheets(user=Depends(get_current_user)):
    owner_id = str(user["_id"])
    google_email = user.get("google_email")

    items = list(
        db["spreadsheet_metadata"].find(
            {"owner_id": owner_id},
            {"_id": 0}
        )
    )

    return {
        "sheets": items,
        "count": len(items),
        "owner_email": user["email"],
        "google_email": google_email
    }
