# api/app/embeddings.py
import requests, os , json

from typing import List

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def embed_text_openrouter(texts: List[str]) -> List[List[float]]:
    """
    ارسال لیست متن به OpenRouter و گرفتن embedding ها
    """
    if not isinstance(texts, list):
        texts = [texts]
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openai/text-embedding-3-small",
                "input": texts
            },
            timeout=10  # Add timeout
        )
        
        # Log the raw response for debugging
        print(f"OpenRouter response status: {resp.status_code}")
        print(f"OpenRouter response content: {resp.text[:500]}")  # First 500 chars
        
        if resp.status_code != 200:
            raise RuntimeError(f"OpenRouter embedding error {resp.status_code}: {resp.text}")
            
        try:
            data = resp.json()
            return [item["embedding"] for item in data["data"]]
        except json.JSONDecodeError:
            raise RuntimeError(f"Failed to parse OpenRouter response as JSON: {resp.text}")
            
    except Exception as e:
        print(f"❌ Embedding request failed: {str(e)}")
        raise
