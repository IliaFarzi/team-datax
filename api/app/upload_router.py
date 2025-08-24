#api/app/upload_router.py
from fastapi import APIRouter, File, UploadFile, HTTPException, Request
from minio import Minio
import pandas as pd
import os
from dotenv import load_dotenv
import tempfile
from datetime import datetime, timezone

from api.app.database import db, get_minio_client, DATAX_MINIO_ENDPOINT, DATAX_MINIO_BUCKET_UPLOADS
from api.app.models import AnalyzeUploadedFileArgs, ListUploadedFilesArgs



load_dotenv(".env")

upload_router = APIRouter(prefix="/upload", tags=["File Upload"])

@upload_router.post("/")
async def upload_file(request: Request, file: UploadFile = File(...)):
    """Upload CSV/Excel to MinIO and store metadata in MongoDB."""
    try:
        # Get google_id from session (or other user identifier)
        google_id = request.session.get("google_id")
        if not google_id:
            raise HTTPException(status_code=401, detail="User not authenticated")
        # Validate file type
        if not (file.filename.endswith(".csv") or file.filename.endswith(".xlsx")):
            raise HTTPException(status_code=400, detail="Only CSV and Excel files are allowed.")

        # Save temporarily
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        # Upload to MinIO
        object_name = f"{google_id}/{file.filename}"
        minio_client = get_minio_client()
        minio_client.fput_object(DATAX_MINIO_BUCKET_UPLOADS, object_name, tmp_path)

        # Read file for metadata
        if file.filename.endswith(".csv"):
            df = pd.read_csv(tmp_path)
        else:
            df = pd.read_excel(tmp_path)

        # Remove temporary file
        os.remove(tmp_path)

        # File URL
        file_url = f"http://{DATAX_MINIO_ENDPOINT}/{DATAX_MINIO_BUCKET_UPLOADS}/{object_name}"

        # Store metadata in MongoDB
        metadata = {
            "google_id": google_id,
            "filename": file.filename,
            "object_name": object_name,
            "bucket": DATAX_MINIO_BUCKET_UPLOADS,
            "url": file_url,
            "rows": len(df),
            "columns": len(df.columns),
            "headers": list(df.columns),
            "uploaded_at": datetime.now(timezone.utc)
        }
        metadata_col = db["uploaded_files"]
        metadata_col.insert_one(metadata)

        return {
            "message": "File uploaded and metadata stored successfully",
            "metadata": metadata
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def list_uploaded_files(google_id: str) -> list:
    """List all files uploaded by a specific user (google_id) with metadata."""
    try:
        metadata_col = db["uploaded_files"]
        files = list(metadata_col.find({"google_id": google_id}, {"_id": 0}))
        return files
    except Exception as e:
        raise ValueError(f"Error retrieving uploaded files: {str(e)}")

def analyze_uploaded_file(filename: str, operation: str = None, column: str = None, value: str = None) -> dict:
    """Analyze an uploaded CSV or Excel file stored in MinIO."""
    try:
        # Retrieve file metadata from MongoDB
        metadata_col = db["uploaded_files"]
        file_metadata = metadata_col.find_one({"filename": filename})
        if not file_metadata:
            raise ValueError(f"File {filename} not found in metadata.")

        # Download file from MinIO
        minio_client = get_minio_client()
        object_name = file_metadata["object_name"]
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv" if filename.endswith(".csv") else ".xlsx") as tmp:
            minio_client.fget_object(DATAX_MINIO_BUCKET_UPLOADS, object_name, tmp.name)
            tmp_path = tmp.name

        # Read file
        if filename.endswith(".csv"):
            df = pd.read_csv(tmp_path)
        else:
            df = pd.read_excel(tmp_path)

        # Remove temporary file
        os.remove(tmp_path)

        # Perform analysis if requested
        if operation:
            if column not in df.columns:
                raise ValueError(f"Column {column} not found in file {filename}.")
            
            if operation == "sum":
                result = pd.to_numeric(df[column], errors="coerce").sum()
                return {"result": result, "operation": "sum", "column": column}
            elif operation == "mean":
                result = pd.to_numeric(df[column], errors="coerce").mean()
                return {"result": result, "operation": "mean", "column": column}
            elif operation == "filter":
                if value is None:
                    raise ValueError("Filter operation requires a value.")
                result = df[df[column].astype(str) == value]
                return {"result": result.to_dict(orient="records"), "operation": "filter", "column": column, "value": value}
            else:
                raise ValueError(f"Unsupported operation: {operation}")
        
        # If no operation specified, return file metadata and headers
        return {
            "filename": filename,
            "headers": list(df.columns),
            "rows": len(df),
            "columns": len(df.columns)
        }

    except Exception as e:
        raise ValueError(f"Error analyzing file {filename}: {str(e)}")
    
    #####