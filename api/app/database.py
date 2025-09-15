#api/app/database.py
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from pymongo.errors import OperationFailure, ConnectionFailure
from pymongo.server_api import ServerApi

import os
import logging
from dotenv import load_dotenv

from minio import Minio
from minio.error import S3Error

# Load environment variables
load_dotenv(".env")

# Logging settings
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# MongoDB config
# =========================
DATAX_MONGO_URI = os.getenv("DB_MONGO_URI")
DATAX_MONGO_DB_NAME = os.getenv("DB_MONGO_NAME")
DATAX_MONGO_COLLECTION_NAME = os.getenv("DB_MONGO_COLLECTION_CHAT_SESSIONS")

# Check for MongoDB environment variables
if not all([DATAX_MONGO_URI, DATAX_MONGO_DB_NAME, DATAX_MONGO_COLLECTION_NAME]):
    print("❌ Missing MongoDB environment variables: DATAX_MONGO_URI, DATAX_MONGO_DB_NAME, DATAX_MONGO_COLLECTION_NAME")
    raise ValueError("MongoDB environment variables are not set")

def get_mongo_client() -> MongoClient:
    """
    Initialize and return a MongoDB client.
    Returns:
        MongoClient: A MongoDB client instance.
    Raises:
        ConnectionFailure: If connection to MongoDB fails.
    """
    try:
        client = MongoClient(DATAX_MONGO_URI, server_api=ServerApi('1'))
        client.admin.command('ping')
        return client
    except ConnectionFailure as e:
        print(f"❌ Failed to connect to MongoDB: {e}")
        raise
    except Exception as e:
        print(f"❌ Unexpected error connecting to MongoDB: {e}")
        raise

def ensure_mongo_collections() -> tuple:
    """
    Return MongoDB client, database, and collections without redundant checks.
    Returns:
        tuple: (MongoClient, database, chat_sessions_collection, users_collection)
    """
    client = get_mongo_client()
    db = client[DATAX_MONGO_DB_NAME]
    chat_sessions_collection = db[DATAX_MONGO_COLLECTION_NAME]
    users_collection = db["users"]
    return client, db, chat_sessions_collection, users_collection

# =========================
# Init check (runs once at import)
# =========================
# MongoDB init
if DATAX_MONGO_URI and DATAX_MONGO_DB_NAME and DATAX_MONGO_COLLECTION_NAME:
    print("\n================ MongoDB Connection Debug ================")
    print(f"📌 DATAX_MONGO_URI: {DATAX_MONGO_URI[:20]}...")  # Hide sensitive part
    print(f"📌 DATAX_MONGO_DB_NAME: {DATAX_MONGO_DB_NAME}")
    print(f"📌 DATAX_MONGO_COLLECTION_NAME: {DATAX_MONGO_COLLECTION_NAME}")
    try:
        mongo_client = get_mongo_client()
        print("✅ MongoDB connection established successfully!")
        mongo_client.close()  # Close to avoid keeping connection open
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
    print("=========================================================\n")

# =========================
# MinIO config
# =========================
STORAGE_MINIO_ENDPOINT = os.getenv("STORAGE_MINIO_ENDPOINT")
STORAGE_MINIO_ACCESS_KEY = os.getenv("STORAGE_MINIO_ACCESS_KEY")
STORAGE_MINIO_SECRET_KEY = os.getenv("STORAGE_MINIO_SECRET_KEY")
STORAGE_MINIO_SECURE = os.getenv("STORAGE_MINIO_SECURE", "False").lower() == "true"
STORAGE_MINIO_BUCKET_SHEETS = os.getenv("STORAGE_MINIO_BUCKET_SHEETS")
STORAGE_MINIO_BUCKET_UPLOADS = os.getenv("STORAGE_MINIO_BUCKET_UPLOADS")

# =========================
# MinIO utilities
# =========================
def get_minio_client() -> Minio:
    """Create and return a MinIO client."""
    client = Minio(
        endpoint=STORAGE_MINIO_ENDPOINT,
        access_key=STORAGE_MINIO_ACCESS_KEY,
        secret_key=STORAGE_MINIO_SECRET_KEY,
        secure=STORAGE_MINIO_SECURE,
    )
    return client


def ensure_bucket(minio_client: Minio, bucket: str):
    """Ensure a bucket exists. If not, create it. Print debug logs."""
    try:
        if not minio_client.bucket_exists(bucket):
            print(f"🪣 Bucket '{bucket}' does not exist. Creating...")
            minio_client.make_bucket(bucket)
            print(f"✅ Bucket '{bucket}' created successfully.")
        else:
            print(f"✅ Bucket '{bucket}' already exists.")
    except Exception as e:
        print(f"❌ Failed to connect/check bucket '{bucket}': {e}")


def minio_file_url(bucket: str, object_name: str) -> str:
    """Return a public-style MinIO URL (for dev/testing)."""
    scheme = "https" if STORAGE_MINIO_SECURE else "http"
    return f"{scheme}://{STORAGE_MINIO_ENDPOINT}/{bucket}/{object_name}"

# =========================
# Init check (runs once at import)
# =========================
if STORAGE_MINIO_ENDPOINT and STORAGE_MINIO_ACCESS_KEY and STORAGE_MINIO_SECRET_KEY and STORAGE_MINIO_BUCKET_SHEETS and STORAGE_MINIO_BUCKET_UPLOADS:
    client = get_minio_client()
    print("\n================ MinIO Connection Debug ================")
    print(f"📌 STORAGE_MINIO_ENDPOINT: {STORAGE_MINIO_ENDPOINT}")
    print(f"📌 STORAGE_MINIO_ACCESS_KEY: {STORAGE_MINIO_ACCESS_KEY}")
    print(f"📌 STORAGE_MINIO_SECRET_KEY: {STORAGE_MINIO_SECRET_KEY[:4]}***")
    print(f"📌 STORAGE_MINIO_BUCKET_SHEETS: {STORAGE_MINIO_BUCKET_SHEETS}")
    print(f"📌 STORAGE_MINIO_BUCKET_UPLOADS: {STORAGE_MINIO_BUCKET_UPLOADS}")
    print(f"📌 STORAGE_MINIO_SECURE: {STORAGE_MINIO_SECURE}")
    print("=========================================================\n")

    # Ensure default buckets exist
    ensure_bucket(client, STORAGE_MINIO_BUCKET_SHEETS)
    ensure_bucket(client, STORAGE_MINIO_BUCKET_UPLOADS)
else:
    print("⚠️ MinIO environment variables are missing. Skipping MinIO init.")
