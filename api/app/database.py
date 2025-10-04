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
DB_MONGO_URI = os.getenv("DB_MONGO_URI")
DB_MONGO_NAME = os.getenv("DB_MONGO_NAME")
DB_MONGO_COLLECTION_CHAT = os.getenv("DB_MONGO_COLLECTION_CHAT")
DB_MONGO_COLLECTION_USERS = os.getenv("DB_MONGO_COLLECTION_USERS")
DB_MONGO_COLLECTION_SESSIONS = os.getenv('DB_MONGO_COLLECTION_SESSIONS')
DB_MONGO_COLLECTION_BILLING = os.getenv('DB_MONGO_COLLECTION_BILLING')
DB_MONGO_COLLECTION_FILE = os.getenv('DB_MONGO_COLLECTION_FILE')
DB_MONGO_COLLECTION_SHEET = os.getenv('DB_MONGO_COLLECTION_SHEET')

# Check for MongoDB environment variables
if not all([DB_MONGO_URI, DB_MONGO_NAME, DB_MONGO_COLLECTION_CHAT, DB_MONGO_COLLECTION_USERS, DB_MONGO_COLLECTION_SESSIONS, DB_MONGO_COLLECTION_BILLING,DB_MONGO_COLLECTION_FILE, DB_MONGO_COLLECTION_SHEET]):
    print("❌ Missing MongoDB environment variables: DB_MONGO_URI, DB_MONGO_NAME, DB_MONGO_COLLECTION_CHAT, DB_MONGO_COLLECTION_USERS, DB_MONGO_COLLECTION_SESSIONS, DB_MONGO_COLLECTION_BILLING,DB_MONGO_COLLECTION_FILE, DB_MONGO_COLLECTION_SHEET")
    raise ValueError("❌ MongoDB environment variables are not set")

def get_mongo_client() -> MongoClient:
    """
    Initialize and return a MongoDB client.
    Returns:
        MongoClient: A MongoDB client instance.
    Raises:
        ConnectionFailure: If connection to MongoDB fails.
    """
    try:
        client = MongoClient(DB_MONGO_URI, server_api=ServerApi('1'))
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
        tuple: (MongoClient, database, chat_collection, users_collection)
    """
    client = get_mongo_client()
    db = client[DB_MONGO_NAME]
    chat_collection = db[DB_MONGO_COLLECTION_CHAT]
    users_collection = db[DB_MONGO_COLLECTION_USERS]
    sessions_collection = db[DB_MONGO_COLLECTION_SESSIONS]
    billing_collection = db[DB_MONGO_COLLECTION_BILLING]
    file_collection = db[DB_MONGO_COLLECTION_FILE]
    sheet_collection = db[DB_MONGO_COLLECTION_SHEET]
    return client, db, chat_collection, users_collection, sessions_collection, billing_collection, file_collection, sheet_collection

# =========================
# Init check (runs once at import)
# =========================
# MongoDB init
if DB_MONGO_URI and DB_MONGO_NAME and DB_MONGO_COLLECTION_CHAT and DB_MONGO_COLLECTION_USERS and DB_MONGO_COLLECTION_SESSIONS and DB_MONGO_COLLECTION_BILLING and DB_MONGO_COLLECTION_FILE and DB_MONGO_COLLECTION_SHEET:
    print("\n================ MongoDB Connection Debug ================")
    print(f"📌 DB_MONGO_URI: {DB_MONGO_URI[:20]}...")  # Hide sensitive part
    print(f"📌 DB_MONGO_NAME: {DB_MONGO_NAME}")
    print(f"📌 DB_MONGO_COLLECTION_CHAT: {DB_MONGO_COLLECTION_CHAT}")
    print(f"📌 DB_MONGO_COLLECTION_USERS: {DB_MONGO_COLLECTION_USERS}")
    print(f"📌 DB_MONGO_COLLECTION_SESSIONS: {DB_MONGO_COLLECTION_SESSIONS}")
    print(f"📌 DB_MONGO_COLLECTION_BILLING: {DB_MONGO_COLLECTION_BILLING}")
    print(f"📌 DB_MONGO_COLLECTION_FILE: {DB_MONGO_COLLECTION_FILE}")
    print(f"📌 DB_MONGO_COLLECTION_SHEET: {DB_MONGO_COLLECTION_SHEET}")

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
STORAGE_MINIO_USERNAME = os.getenv("STORAGE_MINIO_USERNAME")
STORAGE_MINIO_PASSWORD = os.getenv("STORAGE_MINIO_PASSWORD")
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
        access_key=STORAGE_MINIO_USERNAME,
        secret_key=STORAGE_MINIO_PASSWORD,
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
if STORAGE_MINIO_ENDPOINT and STORAGE_MINIO_USERNAME and STORAGE_MINIO_PASSWORD and STORAGE_MINIO_BUCKET_SHEETS and STORAGE_MINIO_BUCKET_UPLOADS:
    client = get_minio_client()
    print("\n================ MinIO Connection Debug ================")
    print(f"📌 STORAGE_MINIO_ENDPOINT: {STORAGE_MINIO_ENDPOINT}")
    print(f"📌 STORAGE_MINIO_USERNAME: {STORAGE_MINIO_USERNAME}")
    print(f"📌 STORAGE_MINIO_PASSWORD: {STORAGE_MINIO_PASSWORD[:4]}***")
    print(f"📌 STORAGE_MINIO_BUCKET_SHEETS: {STORAGE_MINIO_BUCKET_SHEETS}")
    print(f"📌 STORAGE_MINIO_BUCKET_UPLOADS: {STORAGE_MINIO_BUCKET_UPLOADS}")
    print(f"📌 STORAGE_MINIO_SECURE: {STORAGE_MINIO_SECURE}")
    print("=========================================================\n")

    # Ensure default buckets exist
    ensure_bucket(client, STORAGE_MINIO_BUCKET_SHEETS)
    ensure_bucket(client, STORAGE_MINIO_BUCKET_UPLOADS)
else:
    print("⚠️ MinIO environment variables are missing. Skipping MinIO init.")
