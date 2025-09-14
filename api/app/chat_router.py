#api/app/chat_router.py
from fastapi import APIRouter, HTTPException, Request

import datetime
import traceback
from bson import ObjectId

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.runnables import RunnableConfig

from api.app.models import UserMessage
from api.app.database import ensure_mongo_collections
from api.app.session_manager import sessions, initialize_session

client, db, chat_sessions_collection, users_collection = ensure_mongo_collections()

chat_router = APIRouter(prefix="/Chat", tags=['Chat with DATAX'])


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
    
    document = chat_sessions_collection.find_one({"session_id": session_id})
    if not document or "user_id" not in document:
        raise HTTPException(status_code=401, detail="User not authenticated")

    user_id = document["user_id"]
    
    # Continue the usual process
    agent = session["agent"]

    try:
        # ✅ Callback for calculating consumption
        callback = UsageMetadataCallbackHandler()

        response = agent.invoke(
            {"messages": [{"role": "user", "content": content}]},
            config=RunnableConfig(
                configurable={
                    "thread_id": session_id,
                    "recursion_limit": 5,
                },
                callbacks=[callback], # 🔹 Added
            ),
        )

        output = response["messages"][-1].content

        # ✅ Token usage
        input_tokens = output_tokens = total_tokens = 0
        usage = callback.usage_metadata

        if isinstance(usage, dict) and len(usage) > 0:
            stats = next(iter(usage.values()))
            input_tokens = stats.get("input_tokens", 0)
            output_tokens = stats.get("output_tokens", 0)
            total_tokens = stats.get("total_tokens", 0)

        # ✅ Save stats in MongoDB
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$inc": {
            "stats.total_messages": 1,
            "stats.total_input_tokens": input_tokens,
            "stats.total_output_tokens": output_tokens,
            "stats.total_tokens": total_tokens},

            "$set": {"stats.last_message_at": datetime.utcnow()},},
            upsert=True,
        )

        # Save chat history
        save_message(session_id, "user", content)
        save_message(session_id, "assistant", output)

    except Exception as e:
        traceback.print_exc()
        output = f"❗ Error processing response: {str(e)}"
        input_tokens = output_tokens = total_tokens = 0

    return {
        "response": output,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "messages": 1
        }
    }
