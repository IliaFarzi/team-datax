# api/app/embeddings.py
import os
import logging
from langchain_huggingface import HuggingFaceEndpointEmbeddings

logger = logging.getLogger(__name__)

EMBEDDING_HUGGINGFACE_API_KEY = os.getenv("EMBEDDING_HUGGINGFACE_API_KEY")
EMBEDDING_HUGGINGFACE_MODEL = os.getenv("EMBEDDING_HUGGINGFACE_MODEL")

try:
    embedding_model = HuggingFaceEndpointEmbeddings(
        model=EMBEDDING_HUGGINGFACE_MODEL,
        task="feature-extraction",
        huggingfacehub_api_token=EMBEDDING_HUGGINGFACE_API_KEY,
    )
    logger.info(f"✅ HuggingFace embedding model loaded: {EMBEDDING_HUGGINGFACE_MODEL}")
except Exception as e:
    logger.error(f"❌ Failed to load HuggingFace embedding model: {repr(e)}")
    raise


def embed_text(chunks: list[str]) -> list[list[float]]:
    """Convert a list of text chunks into embedding vectors."""
    vectors = []
    for chunk in chunks:
        try:
            vec = embedding_model.embed_query(chunk)
            vectors.append(vec)
            logger.debug(f"🔹 Embedded chunk (len={len(chunk)}): {vec[:5]}...")
        except Exception as e:
            logger.error(f"❌ Embedding failed for chunk='{chunk[:30]}...': {repr(e)}")
    logger.info(f"✅ Created {len(vectors)} embeddings")
    return vectors
