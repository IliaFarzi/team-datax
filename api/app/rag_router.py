# api/app/rag_router.py
from fastapi import APIRouter, Depends
from api.app.models import RagQueryIn
from api.app.auth_router import get_current_user
from api.app.embeddings import embed_text_openrouter
from api.app.vectorstore import search_vectors

rag_router = APIRouter(prefix="/rag", tags=["Dynamic RAG"])

@rag_router.post("/query")
def rag_query(payload: RagQueryIn, user=Depends(get_current_user)):
    owner_id = str(user["_id"])
    query_vector = embed_text_openrouter(payload.question)

    results = search_vectors(owner_id, query_vector, top_k=payload.top_k)

    return {
        "answer": "...",  # Fixed for now, we'll add LLM later
        "sources": [
            {
                "sheet_id": r.payload["sheet_id"],
                "text": r.payload["text"]
            }
            for r in results
        ]
    }
