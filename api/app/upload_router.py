# api/app/upload_router.py
from fastapi import APIRouter, File, UploadFile, HTTPException, Request, Depends, status
import pandas as pd
import os
from dotenv import load_dotenv
import tempfile
from datetime import datetime, timezone
import logging
from bson import ObjectId  # برای کار با _id در MongoDB

from .database import ensure_mongo_collections, get_minio_client, STORAGE_MINIO_ENDPOINT, STORAGE_MINIO_BUCKET_UPLOADS
from .auth_router import get_current_user

load_dotenv(".env")

client, db, chat_collection, users_collection, sessions_collection, billing_collection, file_collection, sheet_collection = ensure_mongo_collections()
logger = logging.getLogger(__name__)

upload_router = APIRouter(prefix="/files", tags=["File Upload to Minio"])

@upload_router.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload any file to MinIO and store metadata in MongoDB."""
    try:
        user_id = str(user["_id"])

        # Save temp file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        logger.debug(f"📌 Temp file saved at {tmp_path}")

        # Check file type
        if not (file.filename.endswith(".csv") or file.filename.endswith(".xlsx")):
            os.remove(tmp_path)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only CSV and Excel (.csv, .xlsx) files are supported."
            )
        
        # Insert base metadata
        base_metadata = {
            "user_id": user_id,
            "filename": file.filename,
            "bucket": STORAGE_MINIO_BUCKET_UPLOADS,
            "created_at": datetime.now(timezone.utc)
        }
        insert_result = file_collection.insert_one(base_metadata)
        file_id = insert_result.inserted_id

        # Upload to MinIO
        object_name = f"{user_id}/{file_id}"
        minio_client = get_minio_client()
        minio_client.fput_object(STORAGE_MINIO_BUCKET_UPLOADS, object_name, tmp_path)
        logger.info(f"✅ File uploaded to MinIO bucket={STORAGE_MINIO_BUCKET_UPLOADS}, object={object_name}")

        # Try reading file metadata
        rows, columns, headers = None, None, []
        try:
            if file.filename.endswith(".csv"):
                df = pd.read_csv(tmp_path)
                rows, columns, headers = len(df), len(df.columns), list(df.columns)
            elif file.filename.endswith(".xlsx"):
                df = pd.read_excel(tmp_path)
                rows, columns, headers = len(df), len(df.columns), list(df.columns)
        except Exception as e:
            logger.warning(f"⚠️ Could not parse file {file.filename} for metadata: {str(e)}")

        os.remove(tmp_path)

        # File URL
        file_url = f"http://{STORAGE_MINIO_ENDPOINT}/{STORAGE_MINIO_BUCKET_UPLOADS}/{object_name}"

        # Update metadata in MongoDB
        update_data = {
            "object_name": object_name,
            "url": file_url,
            "rows": rows,
            "columns": columns,
            "headers": headers,
            "uploaded_at": datetime.now(timezone.utc)
        }
        file_collection.update_one({"_id": file_id}, {"$set": update_data})

        logger.info(f"💾 Metadata stored in Mongo for file={file.filename}")

        return {
            "message": "File uploaded and metadata stored successfully",
            "file_id": str(file_id),
            "metadata": update_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Upload failed for {file.filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Analyze uploaded CSV/Excel file
def analyze_uploaded_file(file_id: str, user_id: str, operation: str, column: str, value: str | None = None):
    file = file_collection.find_one({"_id": ObjectId(file_id)})
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    filename = file["filename"]
    minio_client = get_minio_client()
    object_name = f"{user_id}/{file_id}"
    tmp_path = f"/tmp/{file_id}"

    try:
        # Download file from MinIO
        minio_client.fget_object(STORAGE_MINIO_BUCKET_UPLOADS, object_name, tmp_path)

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

        # Perform operation
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
    files = list(file_collection.find({"user_id": user_id}, {"_id": 0}))
    return files

@upload_router.get('/')
def list_uploaded_files(user=Depends(get_current_user)):
    user_id = str(user["_id"])
    files = list(file_collection.find({"user_id": user_id}))

    # همه‌ی _id ها رو به استرینگ تبدیل می‌کنیم
    for f in files:
        f["_id"] = str(f["_id"])
    return files

