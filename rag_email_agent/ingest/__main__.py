import config
from auth.accounts import get_all_account_ids, get_token_for_account
from graph.client import get_messages_with_body
from ingest.chunking import chunk_text
from ingest.cleaning import html_to_text, strip_quoted
from ingest.db import get_connection, replace_chunks, upsert_email
from ingest.embeddings import embed_text

EXPECTED_EMBEDDING_DIM = 1536


def ingest_account(conn, account_id, token):
    messages = get_messages_with_body(token, top=50)
    for msg in messages:
        body = msg["body"]
        if body["contentType"] == "html":
            text = html_to_text(body["content"])
        else:
            text = body["content"]
        text = strip_quoted(text)

        chunks = chunk_text(text, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
        if not chunks:
            continue

        embeddings = [embed_text(c) for c in chunks]
        if len(embeddings[0]) != EXPECTED_EMBEDDING_DIM:
            raise ValueError(
                f"Embedding dimension {len(embeddings[0])} from "
                f"{config.OPENAI_EMBEDDING_MODEL} does not match schema's "
                f"VECTOR({EXPECTED_EMBEDDING_DIM})"
            )

        with conn.transaction():
            email_id = upsert_email(
                conn,
                account_id,
                msg["id"],
                msg.get("subject"),
                msg["from"]["emailAddress"]["address"],
                msg["receivedDateTime"],
                text,
            )
            replace_chunks(conn, account_id, email_id, list(zip(chunks, embeddings)))

        print(f"Ingested {msg['id']}: {len(chunks)} chunks")


def main():
    conn = get_connection()
    try:
        account_ids = get_all_account_ids(conn)
        if not account_ids:
            print("No provisioned accounts found.")
            return

        for account_id in account_ids:
            try:
                token = get_token_for_account(conn, account_id)
                if not token:
                    print(f"Could not get a token for {account_id}, skipping.")
                    continue

                print(f"--- Ingesting for {account_id} ---")
                ingest_account(conn, account_id, token)
            except Exception as exc:
                print(f"Ingest failed for {account_id}: {type(exc).__name__}: {exc}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
