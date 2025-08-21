#api/app/upload_router.py
from fastapi import APIRouter, File, UploadFile, HTTPException, Request
from minio import Minio
import pandas as pd
import os
from dotenv import load_dotenv
import tempfile
from datetime import datetime, timezone

from api.app.database import db, get_minio_client, DATAX_MINIO_BUCKET_UPLOADS

load_dotenv(".env")

upload_router = APIRouter(prefix="/upload", tags=["File Upload"])


@upload_router.post("/")
async def upload_file(request: Request, file: UploadFile = File(...)):
    """Upload CSV/Excel to MinIO and store metadata in MongoDB."""
    try:
        # Get google_id from session (or other user identifier)
        google_id = request.session.get("google_id", "anonymous")

        # Validate file type
        if not (file.filename.endswith(".csv") or file.filename.endswith(".xlsx")):
            raise HTTPException(status_code=400, detail="Only CSV and Excel files are allowed.")

        # Save temporarily
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        # Upload to MinIO
        object_name = file.filename
        get_minio_client.fput_object(DATAX_MINIO_BUCKET_UPLOADS, object_name, tmp_path)

        # ✅ حالا قبل از حذف tmp_path می‌خونیم
        if file.filename.endswith(".csv"):
            df = pd.read_csv(tmp_path)
        else:
            df = pd.read_excel(tmp_path)

        # بعد از خوندن می‌تونیم حذف کنیم
        os.remove(tmp_path)

        # File URL (static reference to MinIO)
        file_url = f"http://{os.getenv('MINIO_ENDPOINT')}/{DATAX_MINIO_BUCKET_UPLOADS}/{object_name}"

        metadata = {
            "google_id": google_id,
            "filename": object_name,
            "bucket": DATAX_MINIO_BUCKET_UPLOADS,
            "url": file_url,
            "rows": len(df),
            "columns": len(df.columns),
            "headers": list(df.columns),
            "uploaded_at": datetime.now(timezone.utc)
        }

        # Store metadata in MongoDB
        metadata_col = db["uploaded_files"]
        metadata_col.insert_one(metadata)

        return {
            "message": "File uploaded and metadata stored successfully",
            "metadata": metadata
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
