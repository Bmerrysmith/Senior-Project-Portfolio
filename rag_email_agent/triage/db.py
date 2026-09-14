def get_target_emails(conn, account_id, window_start, window_end):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, subject, sender, received_at, raw_body
            FROM emails
            WHERE account_id = %s AND received_at >= %s AND received_at < %s
            ORDER BY received_at
            """,
            (account_id, window_start, window_end),
        )
        columns = ["id", "subject", "sender", "received_at", "raw_body"]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_chunk_embeddings(conn, email_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT embedding FROM email_chunks WHERE email_id = %s ORDER BY chunk_index",
            (email_id,),
        )
        return [row[0] for row in cur.fetchall()]


def sender_context(conn, account_id, sender, exclude_email_id, before, limit):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT subject, received_at, raw_body
            FROM emails
            WHERE account_id = %s AND sender = %s AND id != %s AND received_at < %s
            ORDER BY received_at DESC
            LIMIT %s
            """,
            (account_id, sender, exclude_email_id, before, limit),
        )
        columns = ["subject", "received_at", "raw_body"]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def similar_past_emails(conn, account_id, email_id, before, query_embeddings, limit):
    candidates = {}
    with conn.cursor() as cur:
        for embedding in query_embeddings:
            cur.execute(
                """
                SELECT ec.email_id, MIN(ec.embedding <=> %s) AS distance
                FROM email_chunks ec
                JOIN emails e ON e.id = ec.email_id
                WHERE ec.account_id = %s AND ec.email_id != %s AND e.received_at < %s
                GROUP BY ec.email_id
                ORDER BY distance ASC
                LIMIT %s
                """,
                (embedding, account_id, email_id, before, limit),
            )
            for candidate_id, distance in cur.fetchall():
                if candidate_id not in candidates or distance < candidates[candidate_id]:
                    candidates[candidate_id] = distance

    top_ids = sorted(candidates, key=candidates.get)[:limit]
    if not top_ids:
        return []

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, subject, received_at, raw_body FROM emails WHERE id = ANY(%s)",
            (top_ids,),
        )
        rows = {row[0]: row for row in cur.fetchall()}

    return [
        {"subject": rows[i][1], "received_at": rows[i][2], "raw_body": rows[i][3]}
        for i in top_ids
        if i in rows
    ]


def start_triage_run(conn, account_id, digest_date, expected_count):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO triage_runs (account_id, digest_date, expected_count, actual_count, completed_at)
            VALUES (%s, %s, %s, 0, NULL)
            ON CONFLICT (account_id, digest_date) DO UPDATE
              SET expected_count = EXCLUDED.expected_count,
                  actual_count = 0,
                  completed_at = NULL
            """,
            (account_id, digest_date, expected_count),
        )


def increment_triage_run(conn, account_id, digest_date):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE triage_runs SET actual_count = actual_count + 1 WHERE account_id = %s AND digest_date = %s",
            (account_id, digest_date),
        )


def complete_triage_run(conn, account_id, digest_date):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE triage_runs SET completed_at = now() WHERE account_id = %s AND digest_date = %s",
            (account_id, digest_date),
        )


def get_triage_run(conn, account_id, digest_date):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT expected_count, actual_count, completed_at FROM triage_runs WHERE account_id = %s AND digest_date = %s",
            (account_id, digest_date),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {"expected_count": row[0], "actual_count": row[1], "completed_at": row[2]}


def get_unprocessed_emails(conn, account_id, window_start, window_end):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.subject, e.sender, e.received_at
            FROM emails e
            WHERE e.account_id = %s AND e.received_at >= %s AND e.received_at < %s
              AND NOT EXISTS (SELECT 1 FROM email_summaries es WHERE es.email_id = e.id)
            ORDER BY e.received_at
            """,
            (account_id, window_start, window_end),
        )
        columns = ["subject", "sender", "received_at"]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def upsert_summary(conn, account_id, email_id, summary, urgency):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO email_summaries (account_id, email_id, summary, urgency)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (email_id) DO UPDATE
              SET summary = EXCLUDED.summary,
                  urgency = EXCLUDED.urgency,
                  generated_at = now()
            """,
            (account_id, email_id, summary, urgency),
        )
