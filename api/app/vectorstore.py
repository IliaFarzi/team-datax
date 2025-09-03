# api/app/vectorstore.py
import os
import uuid
import logging
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct
from qdrant_client.http import models as rest

logger = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL")
COLLECTION_NAME = "sheets"

# Connect to Qdrant
try:
    client = QdrantClient(url=QDRANT_URL, prefer_grpc=False, timeout=30, check_compatibility=False)
    logger.info(f"✅ Connected to Qdrant at {QDRANT_URL}")
except Exception as e:
    logger.error(f"❌ Failed to connect to Qdrant: {e}")
    raise


def init_collection(dim: int = 384):
    """Create Qdrant collection if it doesn't exist"""
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


def insert_embeddings(qdrant_client, collection_name, embeddings, metadatas, owner_id):
    """Insert embeddings into Qdrant with unique UUID ids"""
    try:
        points = []
        for vector, metadata in zip(embeddings, metadatas):
            point_id = str(uuid.uuid4())  # ✅ unique id (string)
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={"owner_id": owner_id, **metadata}
                )
            )

        qdrant_client.upsert(collection_name=collection_name, points=points)
        logger.info(f"✅ Inserted {len(points)} embeddings into {collection_name}")

    except Exception as e:
        logger.error(f"❌ Error inserting vectors: {repr(e)}")


def search_vectors(owner_id: str, query_vector: list[float], top_k: int = 5):
    """Search for similar vectors in Qdrant"""
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
