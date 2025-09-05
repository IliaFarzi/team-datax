# api/app/sheet_tools.py
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

import os
from bson import ObjectId
from datetime import datetime, timezone
from typing import Dict, List, Any
import pandas as pd

from fastapi import APIRouter, HTTPException, Request


from minio import Minio
from minio.error import S3Error

from api.app.database import ensure_mongo_collections

client, db, chat_sessions_collection, users_collection = ensure_mongo_collections()

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

def list_google_sheets(user_id: str) -> List[Dict[str, str]]:
    credentials = get_credentials(user_id)
    if not credentials:
        raise ValueError("Not connected to Google Sheets. Please connect first.")
    service = build('drive', 'v3', credentials=credentials)
    results = service.files().list(
        q="mimeType='application/vnd.google-apps.spreadsheet'",
        pageSize=20,
        fields="files(id, name)"
    ).execute()
    items = results.get('files', [])
    return [{"id": item["id"], "name": item["name"]} for item in items]

def preview_google_sheet(sheet_id: str, user_id: str) -> Dict[str, Any]:
    credentials = get_credentials(user_id)
    if not credentials:
        raise ValueError("Not connected to Google Sheets. Please connect first.")
    service = build('sheets', 'v4', credentials=credentials)
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range='A1:Z5'
    ).execute()
    values = result.get('values', [])
    if not values:
        return {"headers": [], "rows": [], "sheet_id": sheet_id}
    headers = values[0]
    rows = values[1:5]
    return {"headers": headers, "rows": rows, "sheet_id": sheet_id}

def load_google_sheet_to_dataframe(sheet_id: str, user_id: str) -> pd.DataFrame:
    credentials = get_credentials(user_id)
    if not credentials:
        raise ValueError("Not connected to Google Sheets. Please connect first.")
    service = build('sheets', 'v4', credentials=credentials)
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range='A1:Z1000'
    ).execute()
    values = result.get('values', [])
    if not values:
        raise ValueError("No data found in the spreadsheet.")
    df = pd.DataFrame(values[1:], columns=values[0])
    return df

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

def list_private_public_sheets(user_id: str) -> Dict[str, List[str]]:
    credentials = get_credentials(user_id)
    if not credentials:
        raise ValueError("Not connected to Google Sheets. Please connect first.")
    service = build('drive', 'v3', credentials=credentials)
    results = service.files().list(
        q="mimeType='application/vnd.google-apps.spreadsheet'",
        fields="files(id, name, sharedWithMeTime, owners)"
    ).execute().get("files", [])
    private_sheets = [{"id": f["id"], "name": f["name"]} for f in results if f.get("owners", [{}])[0].get("me", True)]
    public_sheets = [{"id": f["id"], "name": f["name"]} for f in results if f.get("sharedWithMeTime")]
    return {"private_sheets": private_sheets, "public_sheets": public_sheets}


def extract_headers_to_csv(sheet_id: str, user_id: str, sheet_name: str) -> str:
    credentials = get_credentials(user_id)
    if not credentials:
        raise ValueError("Not connected to Google Sheets. Please connect first.")
    service = build('sheets', 'v4', credentials=credentials)
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range='A1:Z1'
    ).execute()
    headers = result.get('values', [[]])[0]
    if not headers:
        raise ValueError("No headers found in the spreadsheet.")
    df = pd.DataFrame([headers], columns=[f"column_{i+1}" for i in range(len(headers))])
    csv_filename = f"headers_{sheet_id}_{user_id}.csv"
    csv_filepath = os.path.join("temp", csv_filename)
    os.makedirs("temp", exist_ok=True)
    df.to_csv(csv_filepath, index=False)
    return csv_filepath
