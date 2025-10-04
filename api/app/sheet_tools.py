# api/app/sheet_tools.py
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

import os
from bson import ObjectId
from typing import Dict, List, Any
import pandas as pd

from fastapi import APIRouter, Request

from .database import get_minio_client, STORAGE_MINIO_BUCKET_SHEETS
from .database import ensure_mongo_collections

client, db, chat_collection, users_collection, sessions_collection ,billing_collection, file_collection, sheet_collection = ensure_mongo_collections()

google_sheets_preview_router = APIRouter(prefix="/sheets", tags=["Google Sheets for tools"])

def credentials_to_dict(credentials):
    """Convert credentials object to dictionary for session storage"""
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes}

def get_credentials(user_id: str):
    """Get credentials from MongoDB"""
    users_col = db["users"]
    user = users_col.find_one({"_id": ObjectId(user_id)})
    if not user or "google_credentials" not in user:
        return None

    credentials = Credentials(**user["google_credentials"])
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        users_col.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"google_credentials": credentials_to_dict(credentials)}}
        )
    return credentials

# ---------- Helper for safe numeric conversion ----------
def safe_numeric(series: pd.Series):
    """Convert a Pandas Series to numeric safely (invalid -> NaN)."""
    return pd.to_numeric(series, errors="coerce")

# Tools for internal use or reuse

# List of user saved sheets (from Mongo)
def list_google_sheets(user_id: str) -> List[Dict[str, str]]:
    sheets = list(sheet_collection.find(
        {"user_id": user_id},
        {"_id": 0, "sheet_id": 1, "sheet_name": 1}
    ))
    return [{"id": s["sheet_id"], "name": s["sheet_name"]} for s in sheets]

def preview_google_sheet(sheet_id: str, user_id: str) -> Dict[str, Any]:
    minio_client = get_minio_client()
    object_name = f"{user_id}/{sheet_id}.csv"
    tmp_path = f"/tmp/{sheet_id}.csv"

    try:
        minio_client.fget_object(STORAGE_MINIO_BUCKET_SHEETS, object_name, tmp_path)
        df = pd.read_csv(tmp_path)

        headers = df.columns.tolist()
        rows = df.head(5).to_dict(orient="records")

        return {"headers": headers, "rows": rows, "sheet_id": sheet_id}
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def load_google_sheet_to_dataframe(sheet_id: str, user_id: str) -> pd.DataFrame:
    minio_client = get_minio_client()
    object_name = f"{user_id}/{sheet_id}.csv"
    tmp_path = f"/tmp/{sheet_id}.csv"

    try:
        minio_client.fget_object(STORAGE_MINIO_BUCKET_SHEETS, object_name, tmp_path)
        return pd.read_csv(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def analyze_google_sheet(sheet_id: str, user_id: str, operation: str, column: str, value: str = None):
    df = load_google_sheet_to_dataframe(sheet_id, user_id)
    if operation == "sum":
        result = safe_numeric(df[column]).sum()
        return {"result": result, "operation": "sum", "column": column}
    elif operation == "mean":
        result = safe_numeric(df[column]).mean()
        return {"result": result, "operation": "mean", "column": column}
    elif operation == "filter":
        if value:
            result = df[df[column].astype(str) == value]
            return {"result": result.to_dict(), "operation": "filter", "column": column, "value": value}
        else:
            raise ValueError("Filter operation requires a value")
    else:
        raise ValueError(f"Unsupported operation: {operation}")



def extract_headers_to_csv(sheet_id: str, user_id: str, sheet_name: str) -> str:
    df = load_google_sheet_to_dataframe(sheet_id, user_id)
    headers = df.columns.tolist()

    if not headers:
        raise ValueError("No headers found in the sheet")

    csv_filename = f"headers_{sheet_id}_{user_id}.csv"
    csv_filepath = os.path.join("temp", csv_filename)
    os.makedirs("temp", exist_ok=True)

    pd.DataFrame([headers], columns=[f"column_{i+1}" for i in range(len(headers))]).to_csv(csv_filepath, index=False)
    return csv_filepath

