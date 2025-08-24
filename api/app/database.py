#api/app/database.py
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from pymongo.errors import OperationFailure

import os
from dotenv import load_dotenv

from minio import Minio
from minio.error import S3Error

# Load environment variables
load_dotenv(".env")

# Get MongoDB configuration
DATAX_MONGO_URI = os.getenv("DATAX_MONGO_URI")
DATAX_MONGO_DB_NAME = os.getenv("DATAX_MONGO_DB_NAME")
DATAX_MONGO_COLLECTION_NAME = os.getenv("DATAX_MONGO_COLLECTION_NAME")

# Initialize MongoDB client and database
try:
    client = MongoClient(DATAX_MONGO_URI, server_api=ServerApi('1'))
    client.admin.command('ping')
    print("✅ Pinged your deployment. Connected to MongoDB successfully!")
    
    db = client[DATAX_MONGO_DB_NAME]
    chat_sessions_collection = db[DATAX_MONGO_COLLECTION_NAME]
    users_col = db["users"]  # New collection for users
    
    db_list = client.list_database_names()
    if DATAX_MONGO_DB_NAME in db_list:
        print(f"✅ Database '{DATAX_MONGO_DB_NAME}' exists.")
    else:
        print(f"ℹ️  Database '{DATAX_MONGO_DB_NAME}' will be created on first use.")

    try:
        col_list = db.list_collection_names()
        if DATAX_MONGO_COLLECTION_NAME in col_list:
            print(f"✅ Collection '{DATAX_MONGO_COLLECTION_NAME}' exists.")
        else:
            print(f"ℹ️  Collection '{DATAX_MONGO_COLLECTION_NAME}' will be created on first use.")
        
        if "users" in col_list:
            print(f"✅ Collection 'users' exists.")
        else:
            print(f"ℹ️  Collection 'users' will be created on first use.")
    except OperationFailure as e:
        if "not authorized" in str(e):
            print(f"⚠️ Not authorized to list collections. Collections will be created on first use.")
        else:
            raise e

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
if DATAX_MINIO_ENDPOINT and DATAX_MINIO_ACCESS_KEY and DATAX_MINIO_SECRET_KEY:
    client = get_minio_client()
    print("\n================ MinIO Connection Debug ================")
    print(f"📌 DATAX_MINIO_ENDPOINT: {DATAX_MINIO_ENDPOINT}")
    print(f"📌 DATAX_MINIO_ACCESS_KEY: {DATAX_MINIO_ACCESS_KEY}")
    print(f"📌 DATAX_MINIO_SECRET_KEY: {DATAX_MINIO_SECRET_KEY[:4]}***")
    print(f"📌 Secure: {DATAX_MINIO_SECURE}")
    print("=========================================================\n")

    # Ensure default buckets exist
    ensure_bucket(client, DATAX_MINIO_BUCKET_SHEETS)
    ensure_bucket(client, DATAX_MINIO_BUCKET_UPLOADS)
else:
    print("⚠️ MinIO environment variables are missing. Skipping MinIO init.")
