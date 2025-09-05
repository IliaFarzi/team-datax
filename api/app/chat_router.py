#api/app/chat_router.py
from fastapi import APIRouter, HTTPException, Request
import traceback

from api.app.models import UserMessage
from api.app.database import ensure_mongo_collections
from api.app.session_manager import sessions, initialize_session

client, db, chat_sessions_collection, users_collection = ensure_mongo_collections()

chat_router = APIRouter(prefix="/Chat", tags=['Chat with DATAX'])

@chat_router.post("/send_message")
def send_message(message: UserMessage, request:Request):
    session_id = message.session_id
    content = message.content

    
    # If the session does not exist, create it
    if session_id not in sessions:
        _, sessions[session_id], _ = initialize_session(request)

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
    
@chat_router.get("/get_history/{session_id}")
def get_chat_history(session_id: str):
    return get_history(session_id)  # مستقیماً از DB بخون
