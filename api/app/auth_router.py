# api/app/auth_router.py
from fastapi import APIRouter, HTTPException, Depends, Body
from fastapi.security import OAuth2PasswordBearer

from typing import Dict, Any

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

from jose import JWTError, jwt
from passlib.context import CryptContext
from bson import ObjectId

import os
import secrets
import pandas as pd
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv


from api.app.database import ensure_mongo_collections
from api.app.session_manager import sessions
from api.app.ingesting_sheet import ingest_sheet
from api.app.models import SignupIn, LoginIn, VerifyIn, ForgotPasswordIn, ResetPasswordIn, ExchangeCodeIn
from api.app.email_sender import send_otp, send_reset_code

# =========================
# Environment & constants
# =========================
load_dotenv(".env")

client, db, chat_sessions_collection, users_collection = ensure_mongo_collections()

# For local testing only. Remove in production.
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "0"

# Google OAuth settings from environment variables
AUTH_GOOGLE_CLIENT_ID= os.getenv("AUTH_GOOGLE_CLIENT_ID")
AUTH_GOOGLE_CLIENT_SECRET = os.getenv("AUTH_GOOGLE_CLIENT_SECRET")
AUTH_GOOGLE_URI_TOKEN = os.getenv("AUTH_GOOGLE_URI_TOKEN")
AUTH_GOOGLE_URI_AUTH = os.getenv("AUTH_GOOGLE_URI_AUTH")
AUTH_GOOGLE_URI_CERTS = os.getenv("AUTH_GOOGLE_URI_CERTS")
AUTH_GOOGLE_PROJECT_ID = os.getenv('AUTH_GOOGLE_PROJECT_ID')

# Check for the existence of variables
if not all([AUTH_GOOGLE_CLIENT_ID, AUTH_GOOGLE_CLIENT_SECRET, AUTH_GOOGLE_URI_TOKEN, AUTH_GOOGLE_URI_AUTH, AUTH_GOOGLE_URI_CERTS,AUTH_GOOGLE_PROJECT_ID]):
    raise ValueError("Missing Google OAuth environment variables")

# Client settings for Flow
client_config = {
    "web": {
        "client_id": AUTH_GOOGLE_CLIENT_ID,
        "project_id": AUTH_GOOGLE_PROJECT_ID,
        "client_secret": AUTH_GOOGLE_CLIENT_SECRET,
        "auth_uri": AUTH_GOOGLE_URI_AUTH,
        "token_uri": AUTH_GOOGLE_URI_TOKEN,
        "auth_provider_x509_cert_url": AUTH_GOOGLE_URI_CERTS
    }
}

# Frontend callback where Google redirects after Sheets consent
FRONTEND_URL = os.getenv("FRONTEND_URL")
FRONTEND_SHEETS_CALLBACK = f"{FRONTEND_URL}/google-sheets/callback"

# JWT
AUTH_JWT_SECRET = os.getenv("AUTH_JWT_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Google scopes (Sheets connection ONLY)
SCOPES_SHEETS = [
    "openid",
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
    return jwt.encode(to_encode, AUTH_JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        payload = jwt.decode(token, AUTH_JWT_SECRET, algorithms=[ALGORITHM])
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
        user = users_collection.find_one({"_id": ObjectId(user_id)})
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
    existing = users_collection.find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")


    verification_code = ''.join(secrets.choice('0123456789') for _ in range(6))  # 6-digit OTP
    send_otp(payload.email, verification_code)


    user_doc = {
        "full_name": payload.full_name,
        "email": payload.email,
        "phone": payload.phone,
        "password_hash": hash_password(payload.password),
        "verification_code": hash_password(verification_code),
        "otp_expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        "otp_attempts": 0,
        "is_verified": False,
        "created_at": datetime.now(timezone.utc),
        "last_login": None,
        "google_credentials": None,
    }
    result = users_collection.insert_one(user_doc)

    # ⚡ Now we put the real user_id in the token
    token = create_access_token({"sub": str(result.inserted_id)})
    success = {
        "message": "Signup successful. An OTP has been sent to your email. Please verify your account.",
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
    user = users_collection.find_one({"email": payload.email})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # ✅ Prevent login if account is not verified
    if not user.get("is_verified", False):
        raise HTTPException(status_code=403, detail="Account not verified. Please verify your email first.")

    # Update last_login timestamp
    users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login": datetime.now(timezone.utc)}}
    )

    # Generate JWT token and create session
    token = create_access_token({"sub": str(user["_id"])})

    success = {
    "message": "Login successful",
    "token": token,
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
    user = users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Convert otp_expires_at to offset-aware if naive
    otp_expires_at = user.get("otp_expires_at")
    if otp_expires_at and not otp_expires_at.tzinfo:
        otp_expires_at = otp_expires_at.replace(tzinfo=timezone.utc)
        print(f"Converted otp_expires_at to UTC: {otp_expires_at}")  # Debug

    if otp_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP has expired")

    if user.get("otp_attempts", 0) >= 5:
        raise HTTPException(status_code=429, detail="Too many attempts. Request a new OTP.")

    if not verify_password(payload.code, user.get("verification_code")):
        users_collection.update_one({"_id": user["_id"]}, {"$inc": {"otp_attempts": 1}})
        raise HTTPException(status_code=400, detail="Invalid verification code")
    
    users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "is_verified": True,
            "verified_at": datetime.now(timezone.utc),
            "otp_attempts": 0
        }}
    )
    token = create_access_token({"sub": str(user["_id"])})
    success = {
        "message": "Account verified successfully",
        "token": token,
        "email": user.get("email"),
        "id": str(user["_id"]),
        "created_at": user.get("created_at"),
        "is_verified": user.get("is_verified"),
    }
    print(success)
    return success

# =========================
# /auth/reset-password/request
# =========================
@auth_router.post("/reset-password/request")
def request_password_reset(payload: ForgotPasswordIn):
    user = users_collection.find_one({"email": payload.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    reset_code = ''.join(secrets.choice('0123456789') for _ in range(6))
    token = create_access_token({"sub": str(user["_id"])})

    users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "reset_code": pwd_context.hash(reset_code),
            "reset_code_expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            "reset_attempts": 0
        }}
    )

    send_reset_code(payload.email, reset_code)

    success = {
        "message": "Password reset code sent to your email",
        "token":token,
        "email": user.get("email"),
        "user_id": str(user["_id"]),
        "reset_code": reset_code
    }

    print(success)
    return success


# =========================
# /auth/reset-password/confirm
# =========================
@auth_router.post("/reset-password/confirm")
def confirm_password_reset(
    payload: ResetPasswordIn,
    email: str = Depends(get_current_email_from_session)
):
    
    new_password = payload.new_password
    user = users_collection.find_one({"email": email})

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 1. Expiration check
    expires_at = user.get("reset_code_expires_at")
    if not expires_at or expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Reset code expired")

    # 2. Too many attempts
    attempts = user.get("reset_attempts", 0)
    if attempts >= 5:
        raise HTTPException(status_code=403, detail="Too many failed attempts. Request a new code.")

    # 3. Code verification
    hashed_code = user.get("reset_code")
    if not hashed_code or not pwd_context.verify(payload.new_password, hashed_code):
        users_collection.update_one({"_id": user["_id"]}, {"$inc": {"reset_attempts": 1}})
        raise HTTPException(status_code=400, detail="Invalid reset code")

    # 4. Update password
    users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password)}}
    )

    # 5. Clear reset fields
    users_collection.update_one(
        {"_id": user["_id"]},
        {"$unset": {"reset_code": "", "reset_code_expires_at": "", "reset_attempts": ""}}
    )

    # 6. Return token
    token = create_access_token({"sub": str(user["_id"])})

    success = {
        "message": "Password reset successful",
        "token":token,
        "email": user.get("email"),
        "user_id": str(user["_id"]),
    "new_password":  new_password}
    
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
    
    auth_url, state = flow.authorization_url(prompt="consent",
                                             access_type="offline", # Get refresh_token
                                             include_granted_scopes='true')# If the user has previously granted permission, use it again
    sessions[str(user["_id"])] = {"state": state}

    return {"auth_url": auth_url, "state": state}

# Code exchange and data storage
@auth_router.post("/google-sheets/exchange")
def exchange_code_and_ingest(payload: ExchangeCodeIn, user=Depends(get_current_user)):
    stored_state = sessions.get(str(user["_id"]), {}).get("state")
    print("📩 Incoming exchange request")
    print(f"➡️ code: {payload.code}")
    print(f"➡️ state: {payload.state}")
    print(f"➡️ stored_state: {stored_state}")

    if not stored_state or payload.state != stored_state:
        raise HTTPException(status_code=400, detail="Invalid state")

    # Step 1: Exchange code → tokens
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES_SHEETS,
        redirect_uri=FRONTEND_SHEETS_CALLBACK,
    )
    try:
        print("🔑 Fetching token from Google...")
        flow.fetch_token(code=payload.code)
        credentials = flow.credentials
        print("✅ Token fetched successfully")
        print(f"   access_token: {credentials.token[:20]}...")
        print(f"   refresh_token: {credentials.refresh_token}")
    except Exception as e:
        print(f"❌ Error while fetching token: {repr(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to exchange code: {e}")

    # Step 2: Get Google account email
    try:
        oauth2_service = build("oauth2", "v2", credentials=credentials)
        user_info = oauth2_service.userinfo().get().execute()
        google_email = user_info.get("email")
        print(f"📧 Google email: {google_email}")
    except Exception as e:
        print(f"❌ Error fetching user info: {repr(e)}")
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
    users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "google_email": google_email,
            "google_credentials": creds_dict,
            "sheets_connected_at": datetime.now(timezone.utc)
        }},
    )
    print("💾 Credentials saved to Mongo")

    # Step 4: Ingest sheets → MinIO + Qdrant
    try:
        drive = build("drive", "v3", credentials=credentials)
        sheets = drive.files().list(
            q="mimeType='application/vnd.google-apps.spreadsheet'",
            fields="files(id, name)"
        ).execute().get("files", [])

        uploaded_to_minio = []
        skipped_sheets = []
        for f in sheets:
            sheet_id = f["id"]
            sheet_name = f["name"]

            svc = build("sheets", "v4", credentials=credentials)

            try:
                values = svc.spreadsheets().values().get(
                    spreadsheetId=sheet_id,
                    range="A1:Z50"  # preview
                ).execute().get("values", [])
            except Exception as e:
                print(f"❌ Google Sheets API error for {sheet_name}: {repr(e)}")
                skipped_sheets.append({"sheet_name": sheet_name, "error": str(e)})
                continue  # Skips this sheet and moves to the next one
            if not values:
                df = pd.DataFrame()
            else:
                headers = values[0]
                rows = values[1:]
                normalized_rows = [
                    row + [None] * (len(headers) - len(row)) if len(row) < len(headers) else row[:len(headers)]
                    for row in rows
                ]
                df = pd.DataFrame(normalized_rows, columns=headers)

            #⚡ Ingest_sheet is called here
            meta = ingest_sheet(
                user_id=str(user["_id"]),
                sheet_id=sheet_id,
                sheet_name=sheet_name,
                df=df
            )
            uploaded_to_minio.append(meta)


        print(f"📂 Uploaded {len(uploaded_to_minio)} sheets to MinIO + Qdrant")
    except Exception as e:
        print(f"❌ Error ingesting sheets: {repr(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to ingest sheets: {e}")

    # Clear state after successful exchange
    sessions.pop(str(user["_id"]), None)

    return {
        "message": "Google Sheets connected and ingested successfully",
        "google_email": google_email,
        "uploaded_to_minio": uploaded_to_minio,
        "skipped_sheets": skipped_sheets
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
