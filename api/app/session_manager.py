# api/app/config.py
import uuid

sessions = {}
WELCOME_MESSAGE = "👋 **Welcome!** How can I help you today?"
#DEFAULT_MODEL = "mistralai/mistral-7b-instruct"
#DEFAULT_MODEL = "qwen/qwen2.5-72b-instruct"
#DEFAULT_MODEL = "mistralai/mistral-nemo"
DEFAULT_MODEL = "mistralai/mistral-small-3.2-24b-instruct"

def initialize_session(request):
    from api.app.agent import get_agent #lazy import
    from api.app.chat_router import save_message #lazy import
    session_id = str(uuid.uuid4())
    sessions[session_id] = {"agent": get_agent(DEFAULT_MODEL)}
    sessions[session_id] = {"agent": get_agent(DEFAULT_MODEL, request)}
    saving_message = save_message(session_id, "assistant", WELCOME_MESSAGE)
    return session_id, sessions[session_id], saving_message