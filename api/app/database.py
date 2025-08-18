#api/app/database.py
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

import os
from dotenv import load_dotenv

from minio import Minio
from minio.error import S3Error

# Load environment variables
load_dotenv(".env")

# Get MongoDB configuration
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME")

# Initialize MongoDB client and database
try:
    client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
    client.admin.command('ping')
    print("✅ Pinged your deployment. Connected to MongoDB successfully!")
    
    db = client[MONGO_DB_NAME]
    chat_sessions_collection = db[MONGO_COLLECTION_NAME]
    users_col = db["users"]  # New collection for users
    
    db_list = client.list_database_names()
    if MONGO_DB_NAME in db_list:
        print(f"✅ Database '{MONGO_DB_NAME}' exists.")
    else:
        print(f"ℹ️  Database '{MONGO_DB_NAME}' will be created on first use.")

    col_list = db.list_collection_names()
    if MONGO_COLLECTION_NAME in col_list:
        print(f"✅ Collection '{MONGO_COLLECTION_NAME}' exists.")
    else:
        print(f"ℹ️  Collection '{MONGO_COLLECTION_NAME}' will be created on first use.")
    
    if "users" in col_list:
        print(f"✅ Collection 'users' exists.")
    else:
        print(f"ℹ️  Collection 'users' will be created on first use.")

except Exception as e:
    print(f"❌ Error connecting to MongoDB: {e}")
    raise e

def save_message(session_id: str, role: str, content: str):
    try:
        result = chat_sessions_collection.update_one(
            {"session_id": session_id},
            {
                "$push": {"messages": {"role": role, "content": content}},
                "$setOnInsert": {"session_id": session_id}
            },
            upsert=True
        )
    except Exception as e:
        print(f"❗ Error saving message to MongoDB for session {session_id}: {e}")

def get_history(session_id: str) -> list:
    try:
        document = chat_sessions_collection.find_one({"session_id": session_id})
        if document and "messages" in document:
            return document["messages"]
        return []
    except Exception as e:
        print(f"❗ Error retrieving history from MongoDB for session {session_id}: {e}")
        return []

# =========================
# MinIO config
# =========================
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET_SHEETS = os.getenv("MINIO_BUCKET_SHEETS", "spreadsheet-headers")
MINIO_BUCKET_UPLOADS = os.getenv("MINIO_BUCKET_UPLOADS", "user-uploads")

# =========================
# MinIO utilities
# =========================
def get_minio_client() -> Minio:
    """Create and return a MinIO client."""
    client = Minio(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
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
    scheme = "https" if MINIO_SECURE else "http"
    return f"{scheme}://{MINIO_ENDPOINT}/{bucket}/{object_name}"

# =========================
# Init check (runs once at import)
# =========================
if MINIO_ENDPOINT and MINIO_ACCESS_KEY and MINIO_SECRET_KEY:
    client = get_minio_client()
    print("\n================ MinIO Connection Debug ================")
    print(f"📌 MINIO_ENDPOINT: {MINIO_ENDPOINT}")
    print(f"📌 MINIO_ACCESS_KEY: {MINIO_ACCESS_KEY}")
    print(f"📌 MINIO_SECRET_KEY: {MINIO_SECRET_KEY[:4]}***")
    print(f"📌 Secure: {MINIO_SECURE}")
    print("=========================================================\n")

    # Ensure default buckets exist
    ensure_bucket(client, MINIO_BUCKET_SHEETS)
    ensure_bucket(client, MINIO_BUCKET_UPLOADS)
else:
    print("⚠️ MinIO environment variables are missing. Skipping MinIO init.")
