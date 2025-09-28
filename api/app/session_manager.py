# api/app/session_manager.py
import uuid
import os
from dotenv import load_dotenv
from fastapi import Request
from datetime import datetime, timezone

from .database import ensure_mongo_collections

load_dotenv('.env')

client, db, chat_sessions_collection, users_collection, sessions_collection, billing_collection = ensure_mongo_collections()

WELCOME_MESSAGE = (
    "👋 Welcome! My name is **DATAX**. "
    "I’m your data analysis assistant. "
    "I can help you analyze Google Sheets and uploaded files."
)
MODEL_NAME = os.getenv('MODEL_NAME')


def initialize_session(request: Request, user_id: str = None):
    """
    Initialize a new session:
    - Create session_id
    - Build agent config
    - Store in MongoDB (sessions_collection)
    - Insert initial welcome message in chat history
    """
    from .agent import get_agent   # lazy import
    from .chat_router import save_message  # lazy import

    session_id = str(uuid.uuid4())

    # Create an agent with a model and a request
    agent = get_agent(MODEL_NAME, request)

    # Store session in Mongo
    sessions_collection.insert_one({
        "session_id": session_id,
        "user_id": str(user_id) if user_id else None,
        "agent_config": {"model": MODEL_NAME}, # Only config is saved
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    # Initial welcome message
    save_message(session_id, "assistant", WELCOME_MESSAGE)

    return session_id, {"agent": agent}, None


def get_session(session_id: str):
    """
    Retrieve session from Mongo
    """
    return sessions_collection.find_one({"session_id": session_id})
