from fastapi import APIRouter, File, UploadFile, HTTPException, Request, Depends, status

import pandas as pd
import os
from dotenv import load_dotenv
import tempfile
from datetime import datetime, timezone,  timedelta
import logging
from bson import ObjectId  
from minio.error import S3Error

from .database import ensure_mongo_collections, get_minio_client, STORAGE_MINIO_ENDPOINT, STORAGE_MINIO_BUCKET_UPLOADS
from .auth_router import get_current_user


load_dotenv(".env")

client, db, chat_collection, users_collection, sessions_collection, billing_collection, file_collection, sheet_collection = ensure_mongo_collections()
logger = logging.getLogger(__name__)

file_router = APIRouter(tags=["upload, download and delete in file_collection"])

@file_router.post("/upload/files")
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

@file_router.get('/files')
def list_uploaded_files(user=Depends(get_current_user)):
    user_id = str(user["_id"])
    files = list(file_collection.find({"user_id": user_id}))

    # همه‌ی _id ها رو به استرینگ تبدیل می‌کنیم
    for f in files:
        f["_id"] = str(f["_id"])
    return files


def generate_presigned_url(bucket: str, object_name: str, expiry: int = 3600):
    """Generate a presigned URL for downloading from MinIO"""
    minio_client = get_minio_client()
    try:
        url = minio_client.presigned_get_object(
            bucket,
            object_name,
            expires=timedelta(seconds=expiry)
        )
        return url
    except Exception as e:
        logger.error(f"❌ Failed to generate presigned URL: {e}")
        raise HTTPException(status_code=500, detail="Could not generate download link")


@file_router.get('/download/files/{file_id}')
def download_user_file(file_id: str, user=Depends(get_current_user)):
    owner_id = str(user["_id"])

    # اول بررسی در دیتابیس
    file_doc = file_collection.find_one({"_id": ObjectId(file_id), "user_id": owner_id})
    if not file_doc:
        raise HTTPException(status_code=404, detail="File not found or access denied")

    object_name = file_doc.get("object_name")
    bucket = file_doc.get("bucket")

    if not object_name or not bucket:
        raise HTTPException(status_code=500, detail="File metadata is incomplete")

    # ساخت لینک دانلود موقت
    url = generate_presigned_url(bucket, object_name)
    return {"download_url": url}




# Delete a file by ID (MongoDB + MinIO)
@file_router.delete("/delete/files/{file_id}")
def delete_file(file_id: str, user=Depends(get_current_user)):
    """
    DELETE /files/{file_id}
    Delete a file by its ID from both MongoDB (file_collection)
    and MinIO storage. Ensures no partial deletions.
    """
    user_id = str(user["_id"])
    minio_client = get_minio_client()

    # 1️⃣ Find file metadata
    try:
        file_doc = file_collection.find_one({"_id": ObjectId(file_id), "user_id": user_id})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid file ID")

    if not file_doc:
        raise HTTPException(status_code=404, detail="File not found")

    bucket = file_doc.get("bucket")
    object_name = file_doc.get("object_name")

    if not bucket or not object_name:
        raise HTTPException(status_code=500, detail="File metadata missing required fields")

    # 2️⃣ Try deleting from MinIO
    try:
        minio_client.remove_object(bucket, object_name)
        minio_deleted = True
        logger.info(f"✅ Deleted from MinIO: {bucket}/{object_name}")
    except S3Error as e:
        logger.warning(f"⚠️ MinIO object not found or already deleted: {e}")
        minio_deleted = False

    # 3️⃣ Delete from MongoDB
    try:
        result = file_collection.delete_one({"_id": ObjectId(file_id), "user_id": user_id})
        mongo_deleted = result.deleted_count > 0
    except Exception as e:
        logger.error(f"❌ MongoDB deletion failed: {e}")
        mongo_deleted = False

    # 4️⃣ Handle possible partial failures
    if not mongo_deleted and minio_deleted:
        raise HTTPException(status_code=500, detail="File deleted from MinIO but not MongoDB (rollback not possible)")

    if not minio_deleted and mongo_deleted:
        return {
            "message": "File metadata deleted, but MinIO object was missing",
            "fileId": file_id,
            "warning": "MinIO object not found"
        }

    if mongo_deleted and minio_deleted:
        return {"message": "File deleted successfully", "fileId": file_id}

    raise HTTPException(status_code=500, detail="File deletion failed unexpectedly")