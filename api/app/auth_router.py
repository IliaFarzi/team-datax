# api/app/auth_router.py
from fastapi import APIRouter, HTTPException, Request, Depends, Body
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from typing import List, Dict, Any

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

from jose import JWTError, jwt
from passlib.context import CryptContext
from bson import ObjectId

import uuid
import os
import tempfile
import pandas as pd
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from minio import Minio
from minio.error import S3Error

from api.app.database import db
from api.app.agent import get_agent
from api.app.chat_router import sessions, DEFAULT_MODEL, WELCOME_MESSAGE

# =========================
# Environment & constants
# =========================
load_dotenv(".env")

# For local testing only. Remove in production.
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

CLIENT_SECRETS_FILE = os.path.join(os.path.dirname(__file__), "client_secret.json")

# Frontend callback where Google redirects after Sheets consent
FRONTEND_URL = os.getenv("FRONTEND_URL")
FRONTEND_SHEETS_CALLBACK = f"{FRONTEND_URL}/google-sheets/callback"

# JWT
SECRET_KEY = os.getenv("JWT_SECRET", "dev_secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# MinIO
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET = os.getenv("MINIO_BUCKET")

# Google scopes (Sheets connection ONLY)
SCOPES_SHEETS = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
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
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db["users"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# =========================
# Models
# =========================
class SignupIn(BaseModel):
    email: EmailStr
    password: str
    name: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ExchangeCodeIn(BaseModel):
    code: str


# =========================
# MinIO utilities
# =========================
def get_minio_client() -> Minio:
    return Minio(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def ensure_bucket(minio_client: Minio, bucket: str):
    if not minio_client.bucket_exists(bucket):
        minio_client.make_bucket(bucket)


def minio_file_url(bucket: str, object_name: str) -> str:
    # Public-style URL (works if MinIO/ingress serves it). For production, prefer presigned URLs.
    scheme = "https" if MINIO_SECURE else "http"
    return f"{scheme}://{MINIO_ENDPOINT}/{bucket}/{object_name}"


# =========================
# Auth: Email/Password
# =========================
@auth_router.post("/signup")
def signup(payload: SignupIn):
    existing = db["users"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_doc = {
        "email": payload.email,
        "name": payload.name,
        "password_hash": hash_password(payload.password),
        "created_at": datetime.now(timezone.utc),
        "last_login": None,
        "google_credentials": None,
    }
    result = db["users"].insert_one(user_doc)

    token = create_access_token({"sub": str(result.inserted_id)})
    session_id = str(uuid.uuid4())
    sessions[session_id] = {"agent": get_agent(DEFAULT_MODEL)}

    from api.app.database import save_message
    save_message(session_id, "assistant", WELCOME_MESSAGE)

    # Debug log for backend
    signup_data = {
        "message": "Signup successful",
        "token": token,
        "session_id": session_id,
        "user": {
            "id": str(result.inserted_id),
            "email": payload.email,
            "name": payload.name
        }
    }
    print(signup_data)  # Just logs to console

    # Redirect to frontend with query parameters
    redirect_url = (
        f"{FRONTEND_URL}/auth/callback"
        f"?token={token}&session_id={session_id}&name={payload.name}&email={payload.email}"
    )
    return RedirectResponse(url=redirect_url, status_code=302)


@auth_router.post("/login")
def login(payload: LoginIn):
    # Find user by email
    user = db["users"].find_one({"email": payload.email})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Update last_login timestamp
    db["users"].update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login": datetime.now(timezone.utc)}}
    )

    # Generate JWT token and create session
    token = create_access_token({"sub": str(user["_id"])})
    session_id = str(uuid.uuid4())
    sessions[session_id] = {"agent": get_agent(DEFAULT_MODEL)}

    from api.app.database import save_message
    save_message(session_id, "assistant", WELCOME_MESSAGE)

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
    print(login_data)

    # Redirect to frontend with query params
    redirect_url = (
        f"{FRONTEND_URL}/auth/callback"
        f"?token={token}&session_id={session_id}"
        f"&name={user.get('name', '')}&email={user['email']}"
    )
    return RedirectResponse(url=redirect_url, status_code=302)


# ====================================================
# Google Sheets Connect (separate from login/signup)
# ====================================================
@auth_router.get("/connect-google-sheets")
def connect_google_sheets():
    """
    Start Google OAuth for Sheets. We set the redirect_uri to the FRONTEND callback.
    The frontend route (e.g. /google-sheets/callback) receives ?code=... from Google.
    """
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES_SHEETS,
        redirect_uri=FRONTEND_SHEETS_CALLBACK,  # <-- Google will return to frontend
    )
    auth_url, _ = flow.authorization_url(prompt="consent", include_granted_scopes="true")
    # Option A: redirect user immediately
    return RedirectResponse(auth_url)
    # Option B: return {"auth_url": auth_url} and let frontend perform window.location = auth_url


@auth_router.post("/google-sheets/exchange")
def exchange_code_and_ingest(payload: ExchangeCodeIn, user=Depends(get_current_user)):
    """
    Frontend posts the `code` (received in its callback) to this endpoint with Authorization: Bearer <JWT>.
    Backend exchanges code -> tokens, stores credentials, lists sheets, exports CSV to MinIO,
    and stores metadata for frontend display.
    """
    # 1) Exchange code for tokens (redirect_uri must match the one used in /connect-google-sheets)
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES_SHEETS,
        redirect_uri=FRONTEND_SHEETS_CALLBACK,
    )
    try:
        flow.fetch_token(code=payload.code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to exchange code: {e}")

    credentials = flow.credentials

    # 2) Persist Google credentials on the user
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
        {"$set": {"google_credentials": creds_dict, "sheets_connected_at": datetime.now(timezone.utc)}},
    )

    # 3) Read spreadsheet metadata + export CSVs to MinIO
    uploaded: List[Dict[str, Any]] = _ingest_user_sheets_to_minio(user_id=str(user["_id"]), creds=credentials)

    return {
        "message": "Google Sheets connected and ingested successfully",
        "uploaded": uploaded,  # list of files with urls & metadata
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
    ensure_bucket(minio_client, MINIO_BUCKET)

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
            minio_client.fput_object(MINIO_BUCKET, object_name, csv_path)
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

        file_url = minio_file_url(MINIO_BUCKET, object_name)

        # Store/Upsert metadata for listing
        meta = {
            "owner_id": user_id,
            "sheet_id": sheet_id,
            "sheet_name": sheet_name,
            "bucket": MINIO_BUCKET,
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
@auth_router.get("/sheets")
def list_my_sheets(user=Depends(get_current_user)):
    owner_id = str(user["_id"])
    items = list(
        db["spreadsheet_metadata"].find(
            {"owner_id": owner_id},
            {"_id": 0}
        )
    )
    return {"sheets": items}
