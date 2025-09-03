# api/app/sheet_ingest.py
import os
import pandas as pd
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List

from minio.error import S3Error
from api.app.vectorstore import insert_vectors
from api.app.embeddings import embed_text_openrouter
from api.app.database import ensure_mongo_collections, get_minio_client, ensure_bucket, minio_file_url

DATAX_MINIO_BUCKET_SHEETS = os.getenv("DATAX_MINIO_BUCKET_SHEETS")

client, db, chat_sessions_collection, users_collection = ensure_mongo_collections()

def chunk_text(text: str, max_tokens: int = 200) -> List[str]:
    """ساده‌ترین روش chunk کردن: هر N کلمه یک chunk"""
    words = text.split()
    return [
        " ".join(words[i:i+max_tokens])
        for i in range(0, len(words), max_tokens)
    ]


def ingest_sheet(user_id: str, sheet_id: str, sheet_name: str, df: pd.DataFrame) -> Dict[str, Any]:
    """
    Storing CSV in MinIO, storing metadata in Mongo, and inserting vectors in Qdrant
    """
    minio_client = get_minio_client()
    ensure_bucket(minio_client, DATAX_MINIO_BUCKET_SHEETS)

    # Save CSV temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        csv_path = tmp.name
    df.to_csv(csv_path, index=False, encoding="utf-8")

    object_name = f"{user_id}/{sheet_id}.csv"
    try:
        minio_client.fput_object(DATAX_MINIO_BUCKET_SHEETS, object_name, csv_path)
    except S3Error as e:
        os.remove(csv_path)
        raise RuntimeError(f"MinIO upload failed: {e}")
    finally:
        try:
            os.remove(csv_path)
        except Exception:
            pass

    file_url = minio_file_url(DATAX_MINIO_BUCKET_SHEETS, object_name)

    # Build text chunks for RAG
    text_data = df.to_string(index=False)
    chunks = chunk_text(text_data, max_tokens=200)

    # Embed + insert to Qdrant
    vectors = embed_text_openrouter(chunks)
    insert_vectors(user_id, sheet_id, chunks, vectors)

    # Mongo metadata
    meta = {
        "owner_id": user_id,
        "sheet_id": sheet_id,
        "sheet_name": sheet_name,
        "bucket": DATAX_MINIO_BUCKET_SHEETS,
        "object_name": object_name,
        "file_url": file_url,
        "headers": df.columns.tolist(),
        "rows_saved": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "updated_at": datetime.now(timezone.utc),
    }
    db["spreadsheet_metadata"].update_one(
        {"owner_id": user_id, "sheet_id": sheet_id},
        {"$set": meta},
        upsert=True,
    )

    return meta
