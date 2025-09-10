#api/app/chat_router.py
from fastapi import APIRouter, HTTPException, Request

import traceback

from langchain_core.runnables import RunnableConfig

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
    
    # Continue the usual process
    agent = session["agent"]

    try:
        # ✅ Each session_id creates a thread_id for independent memory
        response = agent.invoke(
        {"messages": [{"role": "user", "content": content}]},
        config=RunnableConfig(
            configurable={
                "thread_id": session_id,
                "recursion_limit": 5  # ✅ Put it here, not inside create_react_agent
            }
        ),
    )

        # 🟢 Now the output is a simple string
        output = response

       # 📝 Optional: Still store messages in Mongo for auditing
        save_message(session_id, "user", content)
        save_message(session_id, "assistant", output)

    except Exception as e:
        traceback.print_exc()
        output = f"❗ Error processing response: {str(e)}"

    return {"response": output}


def save_message(session_id: str, role: str, content: str):
    """📌 Optional: Only for archiving in Mongo""" 
    try:
        chat_sessions_collection.update_one(
            {"session_id": session_id},
            {
                "$push": {"messages": {"role": role, "content": content}},
                "$setOnInsert": {"session_id": session_id},
            },
            upsert=True,
        )
    except Exception as e:
        print(f"❗ Error saving message to MongoDB for session {session_id}: {e}")

@chat_router.get("/get_history/{session_id}")
def get_chat_history(session_id: str):
    """📌 Since checkpointer keeps history, this is only for auditing from Mongo"""
    try:
        document = chat_sessions_collection.find_one({"session_id": session_id})
        if document and "messages" in document:
            return document["messages"]
        return []
    except Exception as e:
        print(f"❗ Error retrieving history from MongoDB for session {session_id}: {e}")
        return []