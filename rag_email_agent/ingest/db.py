import psycopg
from pgvector.psycopg import register_vector

import config


def get_connection():
    conn = psycopg.connect(config.SUPABASE_CONNECTION_STRING)
    conn.autocommit = True
    register_vector(conn)
    return conn


def upsert_email(conn, account_id, graph_message_id, subject, sender, received_at, body_text):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO emails (account_id, graph_message_id, subject, sender, received_at, raw_body)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (account_id, graph_message_id) DO UPDATE
              SET subject = EXCLUDED.subject,
                  sender = EXCLUDED.sender,
                  received_at = EXCLUDED.received_at,
                  raw_body = EXCLUDED.raw_body
            RETURNING id
            """,
            (account_id, graph_message_id, subject, sender, received_at, body_text),
        )
        return cur.fetchone()[0]


def replace_chunks(conn, account_id, email_id, chunks_with_embeddings):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM email_chunks WHERE email_id = %s", (email_id,))
        cur.executemany(
            """
            INSERT INTO email_chunks (account_id, email_id, chunk_index, content, embedding)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [
                (account_id, email_id, i, content, embedding)
                for i, (content, embedding) in enumerate(chunks_with_embeddings)
            ],
        )
