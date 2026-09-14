-- Existing embeddings are 768-dim (Ollama nomic-embed-text) and cannot be
-- cast to the new 1536-dim (OpenAI text-embedding-3-small) column type, so
-- clear the table and re-run `python -m ingest` to regenerate chunks +
-- embeddings through the new pipeline. `emails` rows are untouched.
DELETE FROM email_chunks;
ALTER TABLE email_chunks ALTER COLUMN embedding TYPE vector(1536);
