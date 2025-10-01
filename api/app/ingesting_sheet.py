# api/app/ingesting_sheet.py
import os
import logging
import pandas as pd
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List

from minio.error import S3Error
from .database import ensure_mongo_collections, get_minio_client, ensure_bucket, minio_file_url, STORAGE_MINIO_BUCKET_SHEETS

logger = logging.getLogger(__name__)

client, db, chat_collection, users_collection, sessions_collection ,billing_collection = ensure_mongo_collections()

def ingest_sheet(user_id: str, sheet_id: str, sheet_name: str, df: pd.DataFrame) -> Dict[str, Any]:
    """
    Storing CSV in MinIO, storing metadata in Mongo
    """
    minio_client = get_minio_client()
    ensure_bucket(minio_client, STORAGE_MINIO_BUCKET_SHEETS)

    # Save CSV temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        csv_path = tmp.name
    df.to_csv(csv_path, index=False, encoding="utf-8")

    object_name = f"{user_id}/{sheet_id}.csv"
    try:
        minio_client.fput_object(STORAGE_MINIO_BUCKET_SHEETS, object_name, csv_path)
        logger.info(f"✅ Uploaded {object_name} to MinIO bucket {STORAGE_MINIO_BUCKET_SHEETS}")
    except S3Error as e:
        os.remove(csv_path)
        logger.error(f"❌ MinIO upload failed: {e}")
        raise RuntimeError(f"MinIO upload failed: {e}")
    finally:
        try:
            os.remove(csv_path)
        except Exception:
            pass

    file_url = minio_file_url(STORAGE_MINIO_BUCKET_SHEETS, object_name)

    # Mongo metadata 
    meta = {
        "owner_id": user_id,
        "sheet_id": sheet_id,
        "sheet_name": sheet_name,
        "bucket": STORAGE_MINIO_BUCKET_SHEETS,
        "object_name": object_name,
        "filename": f"{sheet_id}.csv",
        "file_url": file_url,
        "headers": df.columns.tolist(),
        "rows_saved": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "updated_at": datetime.now(timezone.utc)
    }

    db["spreadsheet_metadata"].update_one(
        {"owner_id": user_id, "sheet_id": sheet_id},
        {"$set": meta},
        upsert=True,
    )

    logger.info(f"💾 Metadata saved to Mongo for sheet '{sheet_name}' (user={user_id})")
    return meta

