# api/app/embeddings.py
import requests, os , json

def embed_text_openrouter(chunks,OPENROUTER_API_KEY, OPENROUTER_EMBEDDING_URL,EMBEDDING_MODEL):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    
    vectors = []
    for chunk in chunks:
        data = {
            "model": EMBEDDING_MODEL,
            "messages": [
                {"role": "system", "content": "Return ONLY a JSON array of floats as the embedding vector for the given text. No explanation, no extra text."},
                {"role": "user", "content": chunk},
            ],
            "temperature": 0,
            "max_tokens": 512
        }
        resp = requests.post(OPENROUTER_EMBEDDING_URL, headers=headers, json=data)
        try:
            result = resp.json()
        except Exception as e:
            print("❌ Failed to parse JSON:", resp.text[:200])
            raise
        
        content = result["choices"][0]["message"]["content"]
        try:
           vector = json.loads(content)
           if not isinstance(vector, list):
              raise ValueError("Embedding is not a list")
        except Exception:
               print(f"⚠️ Fallback embedding for chunk: {chunk[:50]}...")
               vector = [hash(word) % 1e6 for word in chunk.split()[:100]]
        
        vectors.append(vector)
    
    return vectors

