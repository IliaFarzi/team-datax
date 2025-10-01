# api/app/chat_router.py

from fastapi import APIRouter, HTTPException, Request, Depends
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.runnables import RunnableConfig

from datetime import datetime, timezone
import traceback
import os
from dotenv import load_dotenv
from bson import ObjectId

from .models import UserMessage
from .database import ensure_mongo_collections
from .session_manager import initialize_session, get_session
from .auth_router import get_current_user   # ✅ To extract authenticated user

# Initialize Mongo collections
client, db, chat_collection, users_collection, sessions_collection, billing_collection, file_collection = ensure_mongo_collections()

# Create router
chat_router = APIRouter(prefix="/chat", tags=['Chat with DATAX'])

load_dotenv(".env")
MODEL_NAME = os.getenv('MODEL_NAME')


# =======================================================
# Retrieve full chat history (for auditing/debugging only)
# =======================================================
@chat_router.get("/get_history/{session_id}")
def get_chat_history(session_id: str):
    """
    📌 Retrieve chat history for a given session from MongoDB.
    Since LangChain checkpointer already keeps conversation state,
    this endpoint is mostly for auditing/debugging.
    """
    try:
        document = chat_collection.find_one({"session_id": session_id})
        if document and "messages" in document:
            return document["messages"]
        return []
    except Exception as e:
        print(f"❗ Error retrieving history from MongoDB for session {session_id}: {e}")
        return []


# =======================================================
# Save a single message (user or assistant) into MongoDB
# =======================================================
def save_message(session_id: str, role: str, content: str, usage: dict = None):
    """
    📌 Store messages inside MongoDB, with timestamps and optional usage stats.
    - role: 'user' or 'assistant'
    - content: text content of the message
    - usage: token/cost stats if available
    """
    try:
        message_doc = {
            "role": role,
            "content": content,
            "created_at": datetime.now(timezone.utc),
        }
        if usage:
            message_doc["usage"] = usage

        chat_collection.update_one(
            {"session_id": session_id},
            {
                "$push": {"messages": message_doc},
                "$set": {"timestamps.updated_at": datetime.now(timezone.utc)},
                "$setOnInsert": {
                    "session_id": session_id,
                    "stats": {
                        "total_messages": 0,
                        "total_tokens": 0,
                        "total_spent_usd": 0.0,
                    },
                    "timestamps": {
                        "created_at": datetime.now(timezone.utc)
                    },
                },
            },
            upsert=True,
        )
    except Exception as e:
        print(f"❗ Error saving message to MongoDB for session {session_id}: {e}")


# =======================================================
# Main endpoint: send a user message to the agent
# =======================================================
@chat_router.post("/send_message")
def send_message(message: UserMessage, request: Request, user=Depends(get_current_user)):
    """
    📌 Send a message to the conversational agent and return the assistant's reply.
    - Ensures session exists
    - Builds agent instance on the fly (not stored in Mongo)
    - Tracks token usage and cost
    - Logs chat and billing info to MongoDB
    """

    session_id = message.session_id
    content = message.content

    # ✅ Ensure session exists, otherwise initialize
    session_doc = get_session(session_id)
    if not session_doc:
        initialize_session(request, str(user["_id"]))

    # Check if user is allowed to chat
    if not user.get("can_chat", False):
        raise HTTPException(
            status_code=403,
            detail="You are on the waitlist. Please wait until access is granted."
        )

    # ✅ Rebuild the agent (not persisted in MongoDB, only config is saved)
    from .agent import get_agent
    agent = get_agent(MODEL_NAME, request)

    # Profit margin added to base cost
    PROFIT_MARGIN = 0.2  # 20%

    # 📌 Pricing per 1M tokens (customize per model)
    PRICING = {
        "mistralai/mistral-small-3.2-24b-instruct": {"input": 0.075, "output": 0.20},
        "mistralai/mistral-small-3.2-24b-instruct:free": {"input": 0.0, "output": 0.0},
    }

    try:
        # ✅ Collect token usage via callback
        callback = UsageMetadataCallbackHandler()

        response = agent.invoke(
            {"messages": [{"role": "user", "content": content}]},
            config=RunnableConfig(
                configurable={"thread_id": session_id, "recursion_limit": 5},
                callbacks=[callback],
            ),
        )

        # Extract assistant reply
        output = response["messages"][-1].content

        # ✅ Extract token usage
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

        # ✅ Update user stats in Mongo
        users_collection.update_one(
            {"_id": ObjectId(user["_id"])},
            {
                "$inc": {
                    "stats.total_messages": 1,
                    "stats.total_input_tokens": input_tokens,
                    "stats.total_output_tokens": output_tokens,
                    "stats.total_tokens": total_tokens,
                    "stats.spent_usd": final_cost,
                },
                "$set": {"stats.last_message_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )

        # ✅ Save messages in chat history (both user + assistant)
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
            usage={
                "input_tokens": 0,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "final_cost_usd": final_cost
            }
        )

        # ✅ Update chat-level stats
        chat_collection.update_one(
            {"session_id": session_id},
            {
                "$inc": {
                    "stats.total_messages": 2,  # user + assistant
                    "stats.total_tokens": total_tokens,
                    "stats.total_spent_usd": final_cost,
                },
                "$set": {"timestamps.updated_at": datetime.now(timezone.utc)},
            },
        )

        # ✅ Save billing record
        billing_collection.insert_one({
            "user_id": str(user["_id"]),
            "session_id": str(session_id),
            "model": MODEL_NAME,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost_usd": final_cost,
            "timestamp": datetime.now(timezone.utc)
        })

    except Exception as e:
        traceback.print_exc()
        output = f"❗ Error processing response: {str(e)}"
        input_tokens = output_tokens = total_tokens = 0
        real_cost = final_cost = 0.0

    # ✅ Return response + usage info
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
