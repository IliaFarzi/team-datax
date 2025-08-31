# api/app/services/vectorstore.py
import os
import logging

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest

logger = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL")
COLLECTION_NAME = "sheets"

client = QdrantClient(url=QDRANT_URL)

# Connect to Qdrant
try:
    client = QdrantClient(url=QDRANT_URL)
    logger.info(f"✅ Connected to Qdrant at {QDRANT_URL}")
except Exception as e:
    logger.error(f"❌ Failed to connect to Qdrant at {QDRANT_URL}: {e}")
    raise

# Create collection if it doesn't exist
def init_collection(dim: int = 384):  # Because all-MiniLM has 384-dimensional output
    try:
        collections = client.get_collections().collections
        if not any(c.name == COLLECTION_NAME for c in collections):
            client.recreate_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=rest.VectorParams(size=dim, distance=rest.Distance.COSINE),
            )
            logger.info(f"📦 Collection '{COLLECTION_NAME}' created with dim={dim}")
        else:
            logger.info(f"ℹ️ Collection '{COLLECTION_NAME}' already exists")
    except Exception as e:
        logger.error(f"❌ Error initializing collection: {e}")
        raise

def insert_vectors(owner_id: str, sheet_id: str, chunks: list[str], vectors: list[list[float]]):
    try:
        points = []
        for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
            points.append(
                rest.PointStruct(
                    id=None,
                    vector=vector,
                    payload={
                        "owner_id": owner_id,
                        "sheet_id": sheet_id,
                        "text": chunk,
                    },
                )
            )
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        logger.info(f"➕ Inserted {len(points)} vectors for sheet_id={sheet_id}, owner_id={owner_id}")
    except Exception as e:
        logger.error(f"❌ Error inserting vectors: {e}")
        raise

def search_vectors(owner_id: str, query_vector: list[float], top_k: int = 5):
    try:
        results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=top_k,
            query_filter=rest.Filter(
                must=[rest.FieldCondition(key="owner_id", match=rest.MatchValue(value=owner_id))]
            ),
        )
        logger.info(f"🔍 Search done for owner_id={owner_id}, top_k={top_k}, results={len(results)}")
        return results
    except Exception as e:
        logger.error(f"❌ Error during search: {e}")
        raise
