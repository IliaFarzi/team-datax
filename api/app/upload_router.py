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

upload_router = APIRouter(prefix="/upload", tags=["File Upload"])

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
            "google_id": google_id,
            "filename": file.filename,
            "object_name": object_name,
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

#