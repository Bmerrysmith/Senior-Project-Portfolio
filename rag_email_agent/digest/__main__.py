import sys

from auth.accounts import get_all_account_ids, get_token_for_account
from digest.db import already_sent, get_summaries_for_digest, mark_sent
from digest.formatting import build_digest_html
from graph.client import send_mail
from ingest.db import get_connection
from triage.db import get_triage_run, get_unprocessed_emails
from triage.time_window import previous_day_window


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    window_start, window_end = previous_day_window()
    digest_date = window_start.date()

    conn = get_connection()
    try:
        account_ids = get_all_account_ids(conn)
        if not account_ids:
            print("No provisioned accounts found.")
            return

        for account_id in account_ids:
            try:
                if already_sent(conn, account_id, digest_date):
                    print(f"Digest for {account_id} on {digest_date} already sent, skipping")
                    continue

                grouped = get_summaries_for_digest(conn, account_id, window_start, window_end)
                if not grouped:
                    print(f"No summaries for {account_id} on {digest_date}, skipping")
                    continue

                run = get_triage_run(conn, account_id, digest_date)
                incomplete = run is None or run["completed_at"] is None
                unprocessed = (
                    get_unprocessed_emails(conn, account_id, window_start, window_end)
                    if incomplete
                    else []
                )

                token = get_token_for_account(conn, account_id)
                if not token:
                    print(f"Could not get a token for {account_id}, skipping.")
                    continue

                html_body = build_digest_html(digest_date, grouped, unprocessed)
                send_mail(token, account_id, f"Daily Digest — {digest_date.isoformat()}", html_body)

                mark_sent(conn, account_id, digest_date)
                if unprocessed:
                    print(f"Sent digest for {account_id} on {digest_date} (incomplete: {len(unprocessed)} unprocessed)")
                else:
                    print(f"Sent digest for {account_id} on {digest_date}")
            except Exception as exc:
                print(f"Digest failed for {account_id}: {type(exc).__name__}: {exc}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
