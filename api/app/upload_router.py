#api/app/upload_router.py
from fastapi import APIRouter, File, UploadFile, HTTPException, Request

import pandas as pd
import os
from dotenv import load_dotenv
import tempfile
from datetime import datetime, timezone
import logging

from api.app.database import ensure_mongo_collections, get_minio_client, DATAX_MINIO_ENDPOINT, DATAX_MINIO_BUCKET_UPLOADS

load_dotenv(".env")

client, db, chat_sessions_collection, users_collection = ensure_mongo_collections()
logger = logging.getLogger(__name__)

upload_router = APIRouter(prefix="/upload", tags=["File Upload to Minio"])

# api/app/upload_router.py
@upload_router.post("/")
async def upload_file(request: Request, file: UploadFile = File(...)):
    """Upload any file to MinIO and store metadata in MongoDB."""
    try:
        google_id = request.session.get("google_id")
        if not google_id:
            logger.warning("❌ Upload rejected: user not authenticated")
            raise HTTPException(status_code=401, detail="User not authenticated")

        logger.info(f"📂 Upload attempt by user={google_id}, file={file.filename}")

        # Save temp
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        logger.debug(f"📌 Temp file saved at {tmp_path}")

        # Upload to MinIO
        object_name = f"{google_id}/{file.filename}"
        minio_client = get_minio_client()
        minio_client.fput_object(DATAX_MINIO_BUCKET_UPLOADS, object_name, tmp_path)
        logger.info(f"✅ File uploaded to MinIO bucket={DATAX_MINIO_BUCKET_UPLOADS}, object={object_name}")

        # Try read CSV/Excel for metadata (optional)
        rows, columns, headers = None, None, []
        try:
            if file.filename.endswith(".csv"):
                df = pd.read_csv(tmp_path)
                rows, columns, headers = len(df), len(df.columns), list(df.columns)
            elif file.filename.endswith(".xlsx"):
                df = pd.read_excel(tmp_path)
                rows, columns, headers = len(df), len(df.columns), list(df.columns)
            else:
                logger.info(f"ℹ️ File {file.filename} is not CSV/Excel → skipping row/column metadata")
        except Exception as e:
            logger.warning(f"⚠️ Could not parse file {file.filename} for metadata: {str(e)}")

        os.remove(tmp_path)

        # File URL
        file_url = f"http://{DATAX_MINIO_ENDPOINT}/{DATAX_MINIO_BUCKET_UPLOADS}/{object_name}"

        # Store metadata in MongoDB
        metadata = {
            "owner_id": google_id,
            "filename": file.filename,
            "object_name": object_name,  # user_id/filename
            "bucket": DATAX_MINIO_BUCKET_UPLOADS,
            "url": file_url,
            "rows": rows,
            "columns": columns,
            "headers": headers,
            "uploaded_at": datetime.now(timezone.utc)
        }
        db["uploaded_files"].insert_one(metadata)

        logger.info(f"💾 Metadata stored in Mongo for file={file.filename}")

        return {
            "message": "File uploaded and metadata stored successfully",
            "metadata": metadata
        }

    except Exception as e:
        logger.exception(f"❌ Upload failed for {file.filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Analyze uploaded CSV/Excel file
def analyze_uploaded_file(filename: str, user_id: str, operation: str, column: str, value: str | None = None):
    minio_client = get_minio_client()
    object_name = f"{user_id}/{filename}"
    tmp_path = f"/tmp/{filename}"

    try:
        # Download file from MinIO
        minio_client.fget_object(DATAX_MINIO_BUCKET_UPLOADS, object_name, tmp_path)

        # Load into DataFrame
        if filename.endswith(".csv"):
            df = pd.read_csv(tmp_path)
        elif filename.endswith(".xlsx"):
            df = pd.read_excel(tmp_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        # Check if the column exists
        if column not in df.columns:
            raise HTTPException(status_code=400, detail=f"Column '{column}' not found in file")

        # Simple operation
        if operation == "sum":
            result = df[column].sum()
        elif operation == "mean":
            result = df[column].mean()
        elif operation == "count":
            result = df[column].count()
        elif operation == "filter":
            if value is None:
                raise HTTPException(status_code=400, detail="Value is required for filter operation")
            result = df[df[column] == value].to_dict(orient="records")
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported operation: {operation}")

        return {
            "operation": operation,
            "column": column,
            "result": result,
            "preview": df.head(5).to_dict(orient="records")
        }

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# List of user uploaded files
def list_uploaded_files(user_id: str):
    files = list(db["uploaded_files"].find({"user_id": user_id}, {"_id": 0}))
    return files


######