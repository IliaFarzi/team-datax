#api/app/upload_router.py
from fastapi import APIRouter, File, UploadFile, HTTPException, Request
from minio import Minio
import pandas as pd
import os
from dotenv import load_dotenv
import tempfile
from datetime import datetime, timezone

from api.app.database import db  # MongoDB client

load_dotenv(".env")

upload_router = APIRouter(prefix="/upload", tags=["File Upload"])

# Debug prints for MinIO connection
print("\n================ MinIO Connection Debug ================")
print(f"📌 MINIO_ENDPOINT: {os.getenv('MINIO_ENDPOINT')}")
print(f"📌 MINIO_ACCESS_KEY: {os.getenv('MINIO_ACCESS_KEY')}")
print(f"📌 MINIO_SECRET_KEY: {os.getenv('MINIO_SECRET_KEY')}")
print("=========================================================\n")


# MinIO Client
minio_client = Minio(
    endpoint=os.getenv("MINIO_ENDPOINT"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    secure=False  # For development only
)

BUCKET_NAME = "user-uploads"

# Check connection
try:
    if not minio_client.bucket_exists(BUCKET_NAME):
        print(f"🪣 Bucket '{BUCKET_NAME}' does not exist. Creating...")
        minio_client.make_bucket(BUCKET_NAME)
        print(f"✅ Bucket '{BUCKET_NAME}' created successfully.")
    else:
        print(f"✅ Bucket '{BUCKET_NAME}' already exists.")
except Exception as e:
    print(f"❌ Failed to connect to MinIO: {e}")


@upload_router.post("/")
async def upload_file(request: Request, file: UploadFile = File(...)):
    """Upload CSV/Excel to MinIO and store metadata in MongoDB."""
    try:
        # Get google_id from session (or other user identifier)
        google_id = request.session.get("google_id", "anonymous")

        # Validate file type
        if not (file.filename.endswith(".csv") or file.filename.endswith(".xlsx")):
            raise HTTPException(status_code=400, detail="Only CSV and Excel files are allowed.")

        # Save temporarily
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        # Upload to MinIO
        object_name = file.filename
        minio_client.fput_object(BUCKET_NAME, object_name, tmp_path)

        # Remove temp file
        os.remove(tmp_path)

        # File URL
        file_url = f"http://{os.getenv('MINIO_ENDPOINT')}/{BUCKET_NAME}/{object_name}"

        # Load file to extract metadata
        if file.filename.endswith(".csv"):
            df = pd.read_csv(file_url)
        else:
            df = pd.read_excel(file_url)

        metadata = {
            "google_id": google_id,
            "filename": object_name,
            "bucket": BUCKET_NAME,
            "url": file_url,
            "rows": len(df),
            "columns": len(df.columns),
            "headers": list(df.columns),
            "uploaded_at": datetime.now(timezone.utc)
        }

        # Store metadata in MongoDB
        metadata_col = db["uploaded_files"]
        metadata_col.insert_one(metadata)

        return {
            "message": "File uploaded and metadata stored successfully",
            "metadata": metadata
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def analyze_uploaded_file(filename: str):
    """Download file from MinIO, load into DataFrame, and analyze basic info."""
    try:
        # Download from MinIO to a temporary file
        tmp_path = tempfile.NamedTemporaryFile(delete=False).name
        minio_client.fget_object(BUCKET_NAME, filename, tmp_path)

        # Load into DataFrame
        if filename.endswith(".csv"):
            df = pd.read_csv(tmp_path)
        elif filename.endswith(".xlsx"):
            df = pd.read_excel(tmp_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format.")

        os.remove(tmp_path)

        # Basic analysis
        analysis = {
            "rows": len(df),
            "columns": len(df.columns),
            "headers": list(df.columns),
            "preview": df.head(5).to_dict(orient="records")
        }
        return analysis

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def list_uploaded_files(google_id: str):
    """Return a list of uploaded files for the given google_id."""
    files = list(db["uploaded_files"].find({"google_id": google_id}, {"_id": 0}))
    return files