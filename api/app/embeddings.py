# api/app/embeddings.py
import requests, os
from typing import List

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def embed_text_openrouter(texts: List[str]) -> List[List[float]]:
    """
    ارسال لیست متن به OpenRouter و گرفتن embedding ها
    """
    if not isinstance(texts, list):
        texts = [texts]

    resp = requests.post(
        "https://openrouter.ai/api/v1/embeddings",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "openai/text-embedding-3-small",
            "input": texts
        }
    )

    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter embedding error: {resp.text}")

    data = resp.json()
    return [item["embedding"] for item in data["data"]]
