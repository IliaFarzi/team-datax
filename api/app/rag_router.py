# api/app/rag_router.py
from fastapi import APIRouter, Depends, HTTPException
from api.app.models import RagQueryIn
from api.app.auth_router import get_current_user
from api.app.embeddings import embed_text
from api.app.vectorstore import search_vectors
from api.app.llm import get_rag_agent

rag_router = APIRouter(prefix="/rag", tags=["Dynamic RAG"])

@rag_router.post("/query")
def rag_query(payload: RagQueryIn, user=Depends(get_current_user)):
    owner_id = str(user["_id"])
    query_vector = embed_text(payload.question)[0]

    results = search_vectors(owner_id, query_vector, top_k=payload.top_k)

    context_texts = [r.payload["text"] for r in results]
    stitched_context = "\n\n".join(context_texts)

    # آماده کردن ورودی برای Agent
    agent = get_rag_agent()
    try:
        response = agent.invoke({
            "messages": [
                {"role": "user", "content": f"Context:\n{stitched_context}\n\nQuestion: {payload.question}"}
            ]
        })
        answer = response["messages"][-1].content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")

    return {
        "answer": answer,
        "sources": [
            {"sheet_id": r.payload["sheet_id"], "text": r.payload["text"]}
            for r in results
        ]
    }
