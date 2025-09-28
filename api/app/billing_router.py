# api/app/billing_router.py
from fastapi import APIRouter, Depends
from datetime import datetime, timezone
from .auth_router import get_current_user
from .database import ensure_mongo_collections

client, db, chat_sessions_collection, users_collection, sessions_collection, billing_collection = ensure_mongo_collections()

billing_router = APIRouter(prefix="/billing", tags=["Billing & Usage"])

@billing_router.get("/summary")
def get_billing_summary(user=Depends(get_current_user)):
    user_id = str(user["_id"])

    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": None,
            "total_tokens": {"$sum": "$total_tokens"},
            "total_cost": {"$sum": "$cost_usd"},
            "sessions": {"$addToSet": "$session_id"},
        }}
    ]
    summary = list(billing_collection.aggregate(pipeline))
    if not summary:
        return {"total_tokens": 0, "total_cost": 0.0, "sessions": []}
    
    return {
        "total_tokens": summary[0]["total_tokens"],
        "total_cost_usd": round(summary[0]["total_cost"], 6),
        "sessions": summary[0]["sessions"],
    }

@billing_router.get("/history")
def get_billing_history(user=Depends(get_current_user)):
    user_id = str(user["_id"])
    items = list(
        billing_collection.find({"user_id": user_id}, {"_id": 0}).sort("timestamp", -1)
    )
    return {"count": len(items), "records": items}
