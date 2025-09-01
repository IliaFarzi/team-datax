# api/app/rag_router.py
# api/app/rag_router.py
from fastapi import APIRouter, Depends, HTTPException
from api.app.models import RagQueryIn
from api.app.auth_router import get_current_user
from api.app.embeddings import embed_text_openrouter
from api.app.vectorstore import search_vectors
import requests, os

rag_router = APIRouter(prefix="/rag", tags=["Dynamic RAG"])

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def call_llm(prompt: str) -> str:
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "openai/gpt-3.5-turbo",  # یا هر مدل رایگان دیگری
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that answers questions based on provided context."},
                {"role": "user", "content": prompt}
            ]
        }
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail=f"LLM error: {resp.text}")
    return resp.json()["choices"][0]["message"]["content"]

@rag_router.post("/query")
def rag_query(payload: RagQueryIn, user=Depends(get_current_user)):
    owner_id = str(user["_id"])
    query_vector = embed_text_openrouter(payload.question)[0]

    results = search_vectors(owner_id, query_vector, top_k=payload.top_k)

    context_texts = [r.payload["text"] for r in results]
    stitched_context = "\n\n".join(context_texts)

    prompt = f"Context:\n{stitched_context}\n\nQuestion: {payload.question}\nAnswer:"

    llm_answer = call_llm(prompt)

    return {
        "answer": llm_answer,
        "sources": [
            {
                "sheet_id": r.payload["sheet_id"],
                "text": r.payload["text"]
            }
            for r in results
        ]
    }
