import config
from auth.crypto import decrypt, encrypt
from auth.msal_client import build_msal_app


def is_approved(conn, email):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM approved_users WHERE email = %s", (email,))
        return cur.fetchone() is not None


def get_all_account_ids(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT account_id FROM accounts")
        return [row[0] for row in cur.fetchall()]


def get_priority_context(conn, account_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT priority_context FROM accounts WHERE account_id = %s",
            (account_id,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def upsert_account(conn, account_id, refresh_token):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO accounts (account_id, encrypted_refresh_token)
            VALUES (%s, %s)
            ON CONFLICT (account_id) DO UPDATE
              SET encrypted_refresh_token = EXCLUDED.encrypted_refresh_token
            """,
            (account_id, encrypt(refresh_token)),
        )


def get_token_for_account(conn, account_id):
    """Acquires a fresh access token for account_id using its stored
    encrypted refresh token, rotating and re-storing whatever new refresh
    token MSAL returns. Returns None if no stored token exists for this
    account."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT encrypted_refresh_token FROM accounts WHERE account_id = %s",
            (account_id,),
        )
        row = cur.fetchone()
    if not row:
        return None

    app = build_msal_app()
    result = app.acquire_token_by_refresh_token(decrypt(row[0]), config.GRAPH_SCOPES)

    if not result or "access_token" not in result:
        return None

    if "refresh_token" in result:
        upsert_account(conn, account_id, result["refresh_token"])

    return result["access_token"]
