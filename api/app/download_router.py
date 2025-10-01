# api/app/file_router.py
from fastapi import APIRouter, Depends, HTTPException
from datetime import timedelta
from bson import ObjectId
from .auth_router import get_current_user
from .database import ensure_mongo_collections, get_minio_client
import logging

logger = logging.getLogger(__name__)

file_router = APIRouter(prefix="/files", tags=["File Download"])

client, db, chat_collection, users_collection, sessions_collection, billing_collection, file_collection = ensure_mongo_collections()

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


@file_router.get('/download/{file_id}')
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
