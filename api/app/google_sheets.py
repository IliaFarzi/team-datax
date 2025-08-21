# api/app/google_sheets.py
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

from api.app.database import db, get_minio_client,DATAX_MINIO_BUCKET_SHEETS

import os
from datetime import datetime, timezone
from typing import Dict, List, Any
import pandas as pd

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi import BackgroundTasks

from minio import Minio
from minio.error import S3Error

google_sheets_preview_router = APIRouter(prefix="/sheets", tags=["Google Sheets for tools"])

def credentials_to_dict(credentials):
    """Convert credentials object to dictionary for session storage"""
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

def get_credentials(google_id: str):
    """Get credentials from MongoDB"""
    users_col = db["users"]
    user = users_col.find_one({"google_id": google_id})
    if not user or "google_credentials" not in user:
        return None

    credentials = Credentials(**user["google_credentials"])
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        users_col.update_one(
            {"google_id": google_id},
            {"$set": {"google_credentials": credentials_to_dict(credentials)}}
        )
    return credentials

# ---------- Helper for safe numeric conversion ----------
def safe_numeric(series: pd.Series):
    """Convert a Pandas Series to numeric safely (invalid -> NaN)."""
    return pd.to_numeric(series, errors="coerce")

def upload_to_minio(csv_filepath: str, sheet_id: str, google_id: str, sheet_name: str):
    """Upload CSV file to MinIO and save metadata to MongoDB"""
    
    object_name = f"{google_id}/{sheet_id}.csv"

    # Upload file
    try:
        get_minio_client.fput_object(DATAX_MINIO_BUCKET_SHEETS, object_name, csv_filepath)
        print(f"📤 File uploaded to bucket '{DATAX_MINIO_BUCKET_SHEETS}' as '{object_name}'")
    except S3Error as e:
        print(f"❌ Error uploading to MinIO: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload to MinIO: {str(e)}")

    # Get file URL
    file_url = f"http://{os.getenv('MINIO_ENDPOINT')}/{DATAX_MINIO_BUCKET_SHEETS}/{object_name}"

    # Save metadata to MongoDB
    metadata_col = db["spreadsheet_metadata"]
    metadata_col.update_one(
        {"sheet_id": sheet_id, "google_id": google_id},
        {"$set": {
            "sheet_name": sheet_name,
            "type": "private" if sheet_name in list_private_sheets(google_id) else "public",
            "google_id": google_id,
            "file_path": file_url,
            "uploaded_at": datetime.now(timezone.utc)
        }},
        upsert=True
    )

    # Clean up local file
    os.remove(csv_filepath)
    print(f"🗑️ Deleted local file {csv_filepath}")

    print(f"✅ File {csv_filepath} uploaded to MinIO at {file_url}")
    return file_url

def list_private_sheets(google_id: str) -> List[str]:
    """Return list of private sheet names"""
    credentials = get_credentials(google_id)
    if not credentials:
        raise ValueError("Not connected to Google Sheets. Please connect first.")
    service = build('drive', 'v3', credentials=credentials)
    results = service.files().list(
        q="mimeType='application/vnd.google-apps.spreadsheet'",
        fields="files(id, name, sharedWithMeTime, owners)"
    ).execute().get("files", [])
    return [f["name"] for f in results if f.get("owners", [{}])[0].get("me", True)]

@google_sheets_preview_router.get("/")
async def list_sheets(request: Request):
    """List user's Google Sheets files"""
    credentials = get_credentials(request.session)
    if not credentials:
        raise HTTPException(status_code=401, detail="Not connected to Google Sheets")

    service = build('drive', 'v3', credentials=credentials)

    results = service.files().list(
        q="mimeType='application/vnd.google-apps.spreadsheet'",
        pageSize=10,
        fields="nextPageToken, files(id, name)"
    ).execute()

    items = results.get('files', [])
    return {"sheets": [{"id": item["id"], "name": item["name"]} for item in items]}

@google_sheets_preview_router.get("/{sheet_id}/preview")
async def preview_sheet(sheet_id: str, request: Request):
    """Get the first 5 rows from a Google Sheet"""
    credentials = get_credentials(request.session)
    if not credentials:
        raise HTTPException(status_code=401, detail="Not connected to Google Sheets")

    service = build('sheets', 'v4', credentials=credentials)

    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range='A1:Z5'
    ).execute()

    values = result.get('values', [])

    headers = values[0] if values else []
    rows = values[1:5] if len(values) > 1 else []

    return {
        "headers": headers,
        "rows": rows,
        "sheet_id": sheet_id
    }

@google_sheets_preview_router.get("/{sheet_id}/extract_headers")
async def extract_sheet_headers(sheet_id: str, request: Request, background_tasks: BackgroundTasks):
    """Extract headers from a Google Sheet and save to CSV, then upload to MinIO"""
    google_id = request.session.get('google_id')
    if not google_id:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    # Get sheet name from list_google_sheets
    sheets = list_google_sheets(google_id)
    sheet_name = next((sheet['name'] for sheet in sheets if sheet['id'] == sheet_id), None)
    if not sheet_name:
        raise HTTPException(status_code=404, detail="Sheet not found")

    # Extract headers and save to CSV
    csv_filepath = extract_headers_to_csv(sheet_id, google_id, sheet_name)
    
    # Upload to MinIO and get file URL
    file_url = upload_to_minio(csv_filepath, sheet_id, google_id, sheet_name)
    
    return {"message": f"Headers extracted and uploaded to MinIO", "file_url": file_url}

# Tools for internal use or reuse

def list_google_sheets(google_id: str) -> List[Dict[str, str]]:
    """Return list of user's Google Sheets"""
    credentials = get_credentials(google_id)
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

def preview_google_sheet(sheet_id: str, google_id: str) -> Dict[str, Any]:
    """Preview the first 5 rows of a Google Sheet"""
    credentials = get_credentials(google_id)
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

def load_google_sheet_to_dataframe(sheet_id: str, google_id: str) -> pd.DataFrame:
    """Load entire Google Sheet into a pandas DataFrame"""
    credentials = get_credentials(google_id)
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

def analyze_google_sheet(sheet_id: str, session, operation: str, column: str, value: str = None) -> Dict[str, Any]:
    """Analyze data in a Google Sheet"""
    df = load_google_sheet_to_dataframe(sheet_id, session)
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

def list_private_public_sheets(google_id: str) -> Dict[str, List[str]]:
    credentials = get_credentials(google_id)
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


def extract_headers_to_csv(sheet_id: str, google_id: str, sheet_name: str) -> str:
    """Extract headers from a Google Sheet and save them to a CSV file"""
    credentials = get_credentials(google_id)
    if not credentials:
        raise ValueError("Not connected to Google Sheets. Please connect first.")

    service = build('sheets', 'v4', credentials=credentials)
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range='A1:Z1'  # فقط ردیف اول (هدرها)
    ).execute()

    headers = result.get('values', [[]])[0]
    if not headers:
        raise ValueError("No headers found in the spreadsheet.")

    # Create a DataFrame with headers
    df = pd.DataFrame([headers], columns=[f"column_{i+1}" for i in range(len(headers))])
    
    # Generate a unique filename
    csv_filename = f"headers_{sheet_id}_{google_id}.csv"
    csv_filepath = os.path.join("temp", csv_filename)  # ذخیره موقت در پوشه temp
    
    # Create temp directory if it doesn't exist
    os.makedirs("temp", exist_ok=True)
    
    # Save to CSV
    df.to_csv(csv_filepath, index=False)
    
    return csv_filepath

def extract_headers_tool(sheet_id: str, google_id: str) -> Dict[str, str]:
    """Extract headers from a Google Sheet, save to CSV, and upload to MinIO"""
    sheet_name = next((sheet['name'] for sheet in list_google_sheets(google_id) if sheet['id'] == sheet_id), None)
    if not sheet_name:
        raise ValueError("Sheet not found")
    csv_filepath = extract_headers_to_csv(sheet_id, google_id, sheet_name)
    file_url = upload_to_minio(csv_filepath, sheet_id, google_id, sheet_name)
    return {"file_url": file_url, "sheet_name": sheet_name}