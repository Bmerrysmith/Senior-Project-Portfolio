import requests

import config


def embed_text(text):
    response = requests.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
        json={"model": config.OPENAI_EMBEDDING_MODEL, "input": text},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]
