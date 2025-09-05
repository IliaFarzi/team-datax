# api/app/ingesting_sheet.py
import os
import logging
import pandas as pd
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List

from minio.error import S3Error
from api.app.vectorstore import insert_embeddings, client, COLLECTION_NAME
from api.app.embeddings import embed_text
from api.app.database import ensure_mongo_collections, get_minio_client, ensure_bucket, minio_file_url

logger = logging.getLogger(__name__)

DATAX_MINIO_BUCKET_SHEETS = os.getenv("DATAX_MINIO_BUCKET_SHEETS")

client, db, chat_sessions_collection, users_collection = ensure_mongo_collections()


def chunk_text(text: str, max_tokens: int = 200) -> List[str]:
    """The simplest way to chunk: every N words is a chunk"""
    words = text.split()
    return [
        " ".join(words[i:i + max_tokens])
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
        logger.info(f"✅ Uploaded {object_name} to MinIO bucket {DATAX_MINIO_BUCKET_SHEETS}")
    except S3Error as e:
        os.remove(csv_path)
        logger.error(f"❌ MinIO upload failed: {e}")
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
    logger.info(f"📑 Created {len(chunks)} text chunks from sheet '{sheet_name}'")

    # Try embedding but don't fail the entire ingestion
    embedding_success = False
    try:
        vectors = embed_text(chunks)
        metadatas = [{"chunk": chunk} for chunk in chunks]

        insert_embeddings(client, COLLECTION_NAME, vectors, metadatas, user_id)
        embedding_success = True
        logger.info(f"✅ Successfully embedded and stored chunks for sheet '{sheet_name}'")
    except Exception as e:
        logger.error(f"⚠️ Failed to create embeddings for sheet '{sheet_name}': {str(e)}")

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
        "embedding_success": embedding_success
    }

    db["spreadsheet_metadata"].update_one(
        {"owner_id": user_id, "sheet_id": sheet_id},
        {"$set": meta},
        upsert=True,
    )

    logger.info(f"💾 Metadata saved to Mongo for sheet '{sheet_name}' (user={user_id})")
    return meta
