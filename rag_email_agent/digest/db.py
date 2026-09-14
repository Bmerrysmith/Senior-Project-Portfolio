def get_summaries_for_digest(conn, account_id, window_start, window_end):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT es.urgency, e.subject, e.sender, e.received_at, es.summary
            FROM email_summaries es
            JOIN emails e ON e.id = es.email_id
            WHERE es.account_id = %s AND e.received_at >= %s AND e.received_at < %s
            ORDER BY e.received_at
            """,
            (account_id, window_start, window_end),
        )
        columns = ["urgency", "subject", "sender", "received_at", "summary"]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]

    grouped = {}
    for row in rows:
        grouped.setdefault(row["urgency"], []).append(row)
    return grouped


def already_sent(conn, account_id, digest_date):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM digest_log WHERE account_id = %s AND digest_date = %s",
            (account_id, digest_date),
        )
        return cur.fetchone() is not None


def mark_sent(conn, account_id, digest_date):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO digest_log (account_id, digest_date) VALUES (%s, %s)",
            (account_id, digest_date),
        )
