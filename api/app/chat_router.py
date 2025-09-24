#api/app/chat_router.py
from fastapi import APIRouter, HTTPException, Request

import datetime
import traceback
import os
from dotenv import load_dotenv
from bson import ObjectId

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.runnables import RunnableConfig

from .models import UserMessage
from .database import ensure_mongo_collections
from .session_manager import sessions, initialize_session

client, db, chat_sessions_collection, users_collection = ensure_mongo_collections()

chat_router = APIRouter(prefix="/chat", tags=['Chat with DATAX'])

load_dotenv(".env")


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
    

# ==============================
# api/app/chat_router.py
# ==============================

def save_message(session_id: str, role: str, content: str, usage: dict = None):
    """📌 Store messages inside Mongo with stats and timestamps structure"""
    try:
        message_doc = {
            "role": role,
            "content": content,
            "created_at": datetime.timezone.utc,
        }
        if usage:
            message_doc["usage"] = usage

        chat_sessions_collection.update_one(
            {"session_id": session_id},
            {
                "$push": {"messages": message_doc},
                "$set": {"timestamps.updated_at": datetime.timezone.utc},
                "$setOnInsert": {
                    "session_id": session_id,
                    "stats": {
                        "total_messages": 0,
                        "total_tokens": 0,
                        "total_spent_usd": 0.0,
                    },
                    "timestamps": {
                        "created_at": datetime.timezone.utc,
                        "updated_at": datetime.timezone.utc,
                    },
                },
            },
            upsert=True,
        )
    except Exception as e:
        print(f"❗ Error saving message to MongoDB for session {session_id}: {e}")


@chat_router.post("/send_message")
def send_message(message: UserMessage, request: Request):
    session_id = message.session_id
    content = message.content

    # If the session does not exist, create it
    if session_id not in sessions:
        _, sessions[session_id], _ = initialize_session(request)

    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=403, detail="Invalid or expired session_id.")

    # Find the chat document to get the user_id
    document = chat_sessions_collection.find_one({"session_id": session_id})
    if not document:
        raise HTTPException(status_code=404, detail="Chat session not found")

    user_id = document["user_id"] if "user_id" in document else document["_id"]

    agent = session["agent"]

    MODEL_NAME = os.getenv('MODEL_NAME')
    PROFIT_MARGIN = 0.2  # 20%

    # 📌 Pricing per 1M tokens
    PRICING = {
        "mistralai/mistral-small-3.2-24b-instruct": {"input": 0.075, "output": 0.20},
        "mistralai/mistral-small-3.2-24b-instruct:free": {"input": 0.0, "output": 0.0},
    }

    try:
        # ✅ Callback for calculating consumption
        callback = UsageMetadataCallbackHandler()

        response = agent.invoke(
            {"messages": [{"role": "user", "content": content}]},
            config=RunnableConfig(
                configurable={"thread_id": session_id, "recursion_limit": 5},
                callbacks=[callback],
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

        # ✅ Calculate costs
        price = PRICING.get(MODEL_NAME, {"input": 0, "output": 0})
        input_cost = (input_tokens / 1_000_000) * price["input"]
        output_cost = (output_tokens / 1_000_000) * price["output"]
        real_cost = input_cost + output_cost
        final_cost = real_cost * (1 + PROFIT_MARGIN)

        # ✅ Save usage to users collection
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$inc": {
                    "stats.total_messages": 1,
                    "stats.total_input_tokens": input_tokens,
                    "stats.total_output_tokens": output_tokens,
                    "stats.total_tokens": total_tokens,
                    "stats.spent_usd": final_cost,
                },
                "$set": {"stats.last_message_at": datetime.timezone.utc},
            },
            upsert=True,
        )

        # ✅ Save chat history (user + assistant)
        save_message(
            session_id,
            "user",
            content,
            usage={"input_tokens": input_tokens, "output_tokens": 0, "total_tokens": input_tokens}
        )
        save_message(
            session_id,
            "assistant",
            output,
            usage={"input_tokens": 0, "output_tokens": output_tokens, "total_tokens": total_tokens, "final_cost_usd": final_cost}
        )

        # ✅ Update chat-level stats
        chat_sessions_collection.update_one(
            {"session_id": session_id},
            {
                "$inc": {
                    "stats.total_messages": 2,  # user + assistant
                    "stats.total_tokens": total_tokens,
                    "stats.total_spent_usd": final_cost,
                },
                "$set": {"timestamps.updated_at": datetime.timezone.utc},
            },
        )

    except Exception as e:
        traceback.print_exc()
        output = f"❗ Error processing response: {str(e)}"
        input_tokens = output_tokens = total_tokens = 0
        real_cost = final_cost = 0.0

    return {
        "response": output,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "real_cost_usd": round(real_cost, 6),
            "final_cost_usd": round(final_cost, 6),
            "messages": 1,
        },
    }

