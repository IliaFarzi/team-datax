# api/app/session_manager.py
import uuid
import os
from dotenv import load_dotenv
from fastapi import Request

load_dotenv('.env')

sessions = {}
WELCOME_MESSAGE = "👋 Welcome! My name is **DATAX**. I’m your data analysis assistant. I can help you analyze Google Sheets and uploaded files."
MODEL_NAME = os.getenv('MODEL_NAME')

def initialize_session(request:Request):
    from .agent import get_agent #lazy import
    from .chat_router import save_message #lazy import
    session_id = str(uuid.uuid4())
    # Create an agent with a model and a request
    agent = get_agent(MODEL_NAME, request)
    # Save in session memory
    sessions[session_id] = {"agent": agent}

    # Initial welcome message
    save_message(session_id, "assistant", WELCOME_MESSAGE)
    return session_id, sessions[session_id], None