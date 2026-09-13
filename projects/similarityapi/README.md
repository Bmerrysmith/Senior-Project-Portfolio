# SimilarityAPI

A semantic similarity service for validating a candidate answer against a knowledge base. Given an answer and (optionally) a Qdrant collection to check it against, it returns a similarity score and the supporting content it was compared to.

## How it works

1. **Embed** — the candidate answer is embedded with OpenAI's `text-embedding-ada-002`.
2. **Retrieve** — if no direct comparison text is supplied, the embedding is used to search a Qdrant collection for the closest matching stored content.
3. **Compare** — both the candidate answer and the retrieved content are tokenized (`gensim.utils.simple_preprocess`), used to train a small Word2Vec model on the fly, and reduced to vectors via summed word embeddings.
4. **Score** — cosine similarity between the two vectors is returned as a percentage, alongside the Qdrant payloads that were compared against.

This two-path design (direct-comparison vs. Qdrant-backed retrieval) lets the same endpoint validate an answer against either a fixed reference text or a live knowledge base.

## API

`POST /similarity`

```json
{
  "answer": "the text to check",
  "data": "optional — compare directly against this text instead of Qdrant",
  "collection": "optional — Qdrant collection name, defaults to QDRANT_COLLECTION_NAME"
}
```

Returns `{"result": "87%", "qdrant_content": [...]}`.

## Running it

Set `OPENAI_API_KEY`, `QDRANT_HOST`, `QDRANT_API_KEY`, and `QDRANT_COLLECTION_NAME` (a `.env` file works via `python-dotenv`), then:

```bash
pip install -r requirements.txt
python main.py
```

Or with Docker:

```bash
docker build -t similarity-api .
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=... -e QDRANT_HOST=... -e QDRANT_API_KEY=... -e QDRANT_COLLECTION_NAME=... \
  similarity-api
```
