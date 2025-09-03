# api/app/embeddings.py
import os
import logging
from langchain_huggingface import HuggingFaceEndpointEmbeddings

logger = logging.getLogger(__name__)

HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
HUGGINGFACE_EMBEDDING_MODEL = os.getenv("HUGGINGFACE_EMBEDDING_MODEL")

try:
    embedding_model = HuggingFaceEndpointEmbeddings(
        model=HUGGINGFACE_EMBEDDING_MODEL,
        task="feature-extraction",
        huggingfacehub_api_token=HUGGINGFACE_API_KEY,
    )
    logger.info(f"✅ HuggingFace embedding model loaded: {HUGGINGFACE_EMBEDDING_MODEL}")
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
