# api/app/session_manager.py
import uuid
from fastapi import Request

sessions = {}
WELCOME_MESSAGE = "👋 Welcome! My name is **DATAX**. I’m your data analysis assistant. I can help you analyze Google Sheets and uploaded files."
#DEFAULT_MODEL = "mistralai/mistral-7b-instruct"
#DEFAULT_MODEL = "qwen/qwen2.5-72b-instruct"
#DEFAULT_MODEL = "mistralai/mistral-nemo"
DEFAULT_MODEL = "mistralai/mistral-small-3.2-24b-instruct"

def initialize_session(request:Request):
    from api.app.agent import get_agent #lazy import
    from api.app.chat_router import save_message #lazy import
    session_id = str(uuid.uuid4())
    # Create an agent with a model and a request
    agent = get_agent(DEFAULT_MODEL, request)
    # Save in session memory
    sessions[session_id] = {"agent": agent}

    # Initial welcome message
    save_message(session_id, "assistant", WELCOME_MESSAGE)
    return session_id, sessions[session_id], None