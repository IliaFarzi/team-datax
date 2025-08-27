#api/app/chat_router.py
from fastapi import APIRouter, HTTPException, Request
import traceback

from api.app.models import UserMessage
from api.app.database import save_message, get_history
from api.app.config import sessions, DEFAULT_MODEL, WELCOME_MESSAGE, initialize_session

chat_router = APIRouter(prefix="/Chat", tags=['Chat with LLM'])

@chat_router.post("/send_message")
def send_message(message: UserMessage, request:Request):
    session_id = message.session_id
    content = message.content

    
    # If the session does not exist, create it
    if session_id not in sessions:
        _, sessions[session_id], _ = initialize_session()

    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=403, detail="Invalid or expired session_id.")

    # Save the user's message first
    save_message(session_id, "user", content) # We moved this line here because the model must first have a message from the user in addition to its own message for the history to work properly.

    
    # Get the history AFTER saving the user message
    history = get_history(session_id)

    # Check message count (now including the new user message)
    user_message_count = sum(1 for msg in history if msg["role"] == "user")
    if user_message_count > 20: 
        return {
            "response": "⚠️ You can only send 20 messages in this session. Please start a new session."}

    # Continue the usual process
    agent = session["agent"]
    
    
    try:
        response = agent.invoke({
            "messages": history,
            "session": request.session  # Transfer session to agent
        })
        ai_message = response["messages"][-1]
        output = ai_message.content
        # Save the AI's response
        save_message(session_id, "assistant", output)
    except Exception as e:
        traceback.print_exc()
        output = f"❗ Error processing response: {str(e)}"
        # Even if processing fails, the user message is already saved.
    return {"response": output}

@chat_router.get("/get_history/{session_id}")
def get_chat_history(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return get_history(session_id)
