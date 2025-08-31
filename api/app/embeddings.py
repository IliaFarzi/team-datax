# api/app/embeddings.py
import requests, os

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def embed_text_openrouter(text: str):
    resp = requests.post(
        "https://openrouter.ai/api/v1/embeddings",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "openai/text-embedding-3-small",
            "input": text
        }
    )
    data = resp.json()
    return data["data"][0]["embedding"]
