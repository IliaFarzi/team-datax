#api/app/database.py
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import os
from dotenv import load_dotenv

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