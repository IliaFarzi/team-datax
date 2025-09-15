from fastapi import APIRouter, Depends, HTTPException
from datetime import timedelta
from api.app.auth_router import get_current_user
from api.app.database import ensure_mongo_collections, get_minio_client
import logging

logger = logging.getLogger(__name__)

file_router = APIRouter(prefix="/files", tags=["File Download"])

client, db, chat_sessions_collection, users_collection = ensure_mongo_collections()

from api.app.database import STORAGE_MINIO_BUCKET_SHEETS, STORAGE_MINIO_BUCKET_UPLOADS

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
    
@file_router.get('/files/download/{filename}')    
def download_user_file(filename: str, user=Depends(get_current_user)):
    owner_id = str(user["_id"])
    
    # first search in sheets
    try:
        object_name = f"{owner_id}/{filename}"
        url = generate_presigned_url(STORAGE_MINIO_BUCKET_SHEETS, object_name)
        return {"download_url": url}
    except:
        pass

    # second search in uploads
    try:
        object_name = f"{owner_id}/{filename}"
        url = generate_presigned_url(STORAGE_MINIO_BUCKET_UPLOADS, object_name)
        return {"download_url": url}
    except:
        pass

    raise HTTPException(status_code=404, detail="File not found in any bucket")

