#api/app/database.py
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from pymongo.errors import OperationFailure, ConnectionError
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

# Get MongoDB settings from environment variables
DATAX_MONGO_URI = os.getenv("DATAX_MONGO_URI")
DATAX_MONGO_DB_NAME = os.getenv("DATAX_MONGO_DB_NAME")
DATAX_MONGO_COLLECTION_NAME = os.getenv("DATAX_MONGO_COLLECTION_NAME")

# Check for the existence of environment variables
if not all([DATAX_MONGO_URI, DATAX_MONGO_DB_NAME, DATAX_MONGO_COLLECTION_NAME]):
    logger.error("Missing MongoDB environment variables: DATAX_MONGO_URI, DATAX_MONGO_DB_NAME, DATAX_MONGO_COLLECTION_NAME")
    raise ValueError("MongoDB environment variables are not set")

def get_mongo_client() -> MongoClient:
    """
    Initialize and return a MongoDB client.
    Returns:
        MongoClient: A MongoDB client instance.
    Raises:
        ConnectionError: If connection to MongoDB fails.
    """
    try:
        client = MongoClient(DATAX_MONGO_URI, server_api=ServerApi('1'))
        client.admin.command('ping')
        logger.info("✅ Pinged your deployment. Connected to MongoDB successfully!")
        return client
    except ConnectionError as e:
        logger.error(f"❌ Failed to connect to MongoDB: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error connecting to MongoDB: {e}")
        raise

def ensure_mongo_collections() -> tuple:
    """
    Ensure MongoDB database and collections exist.
    Returns:
        tuple: (MongoClient, database, chat_sessions_collection, users_collection)
    Raises:
        ValueError: If environment variables are missing.
        ConnectionError: If connection to MongoDB fails.
    """
    try:
        client = get_mongo_client()
        db = client[DATAX_MONGO_DB_NAME]
        chat_sessions_collection = db[DATAX_MONGO_COLLECTION_NAME]
        users_collection = db["users"]

        # Check the existence of the database
        db_list = client.list_database_names()
        if DATAX_MONGO_DB_NAME in db_list:
            logger.info(f"✅ Database '{DATAX_MONGO_DB_NAME}' exists.")
        else:
            logger.info(f"ℹ️ Database '{DATAX_MONGO_DB_NAME}' will be created on first use.")

        # Checking for the existence of collections
        col_list = db.list_collection_names()
        if DATAX_MONGO_COLLECTION_NAME in col_list:
            logger.info(f"✅ Collection '{DATAX_MONGO_COLLECTION_NAME}' exists.")
        else:
            logger.info(f"ℹ️ Collection '{DATAX_MONGO_COLLECTION_NAME}' will be created on first use.")
        
        if "users" in col_list:
            logger.info(f"✅ Collection 'users' exists.")
        else:
            logger.info(f"ℹ️ Collection 'users' will be created on first use.")
        
        return client, db, chat_sessions_collection, users_collection

    except OperationFailure as e:
        if "not authorized" in str(e):
            logger.warning(f"⚠️ Not authorized to list collections. Collections will be created on first use.")
            return client, db, chat_sessions_collection, users_collection
        else:
            logger.error(f"❌ MongoDB operation failed: {e}")
            raise
    except Exception as e:
        logger.error(f"❌ Error ensuring MongoDB collections: {e}")
        raise

# Example of use with Context Manager
def with_mongo_client():
    """
    Context manager for MongoDB client to ensure proper closure.
    """
    client = None
    try:
        client = get_mongo_client()
        yield client
    finally:
        if client:
            client.close()
            logger.info("✅ MongoDB client closed.")

# =========================
# MinIO config
# =========================
DATAX_MINIO_ENDPOINT = os.getenv("DATAX_MINIO_ENDPOINT")
DATAX_MINIO_ACCESS_KEY = os.getenv("DATAX_MINIO_ACCESS_KEY")
DATAX_MINIO_SECRET_KEY = os.getenv("DATAX_MINIO_SECRET_KEY")
DATAX_MINIO_SECURE = os.getenv("DATAX_MINIO_SECURE")
DATAX_MINIO_BUCKET_SHEETS = os.getenv("DATAX_MINIO_BUCKET_SHEETS")
DATAX_MINIO_BUCKET_UPLOADS = os.getenv("DATAX_MINIO_BUCKET_UPLOADS")

# =========================
# MinIO utilities
# =========================
def get_minio_client() -> Minio:
    """Create and return a MinIO client."""
    client = Minio(
        endpoint=DATAX_MINIO_ENDPOINT,
        access_key=DATAX_MINIO_ACCESS_KEY,
        secret_key=DATAX_MINIO_SECRET_KEY,
        secure=DATAX_MINIO_SECURE,
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
    scheme = "https" if DATAX_MINIO_SECURE else "http"
    return f"{scheme}://{DATAX_MINIO_ENDPOINT}/{bucket}/{object_name}"

# =========================
# Init check (runs once at import)
# =========================
if DATAX_MINIO_ENDPOINT and DATAX_MINIO_ACCESS_KEY and DATAX_MINIO_SECRET_KEY and DATAX_MINIO_BUCKET_SHEETS and DATAX_MINIO_BUCKET_UPLOADS:
    client = get_minio_client()
    print("\n================ MinIO Connection Debug ================")
    print(f"📌 DATAX_MINIO_ENDPOINT: {DATAX_MINIO_ENDPOINT}")
    print(f"📌 DATAX_MINIO_ACCESS_KEY: {DATAX_MINIO_ACCESS_KEY}")
    print(f"📌 DATAX_MINIO_SECRET_KEY: {DATAX_MINIO_SECRET_KEY[:4]}***")
    print(f"📌 DATAX_MINIO_BUCKET_SHEETS: {DATAX_MINIO_BUCKET_SHEETS}")
    print(f"📌 DATAX_MINIO_BUCKET_UPLOADS: {DATAX_MINIO_BUCKET_UPLOADS}")
    print(f"📌 DATAX_MINIO_SECURE: {DATAX_MINIO_SECURE}")
    print("=========================================================\n")

    # Ensure default buckets exist
    ensure_bucket(client, DATAX_MINIO_BUCKET_SHEETS)
    ensure_bucket(client, DATAX_MINIO_BUCKET_UPLOADS)
else:
    print("⚠️ MinIO environment variables are missing. Skipping MinIO init.")
