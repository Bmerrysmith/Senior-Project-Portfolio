"""AWS Lambda entry point for the daily pipeline.

Runs the three existing phases in the same order as the local
`python -m ingest && python -m triage && python -m digest` sequence. On an
unhandled failure it makes a best-effort attempt to email the traceback to
the user (via the same Graph `Mail.Send` path the digest uses) and then
re-raises so Lambda records the invocation as an error and the EventBridge
Scheduler retry fires.

Idempotency is already handled downstream: `digest_log` prevents a second
digest per day and `triage_runs` tracks partial completion, so a retry of
the whole pipeline is safe.
"""
import logging
import traceback

from digest.__main__ import main as run_digest
from ingest.__main__ import main as run_ingest
from triage.__main__ import main as run_triage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag-email-agent")


def _notify_failure(tb_str):
    """Best-effort failure email. Never raises — the original exception must
    be what propagates out of the handler."""
    try:
        from auth.accounts import get_all_account_ids, get_token_for_account
        from graph.client import send_mail
        from ingest.db import get_connection

        conn = get_connection()
        try:
            for account_id in get_all_account_ids(conn):
                token = get_token_for_account(conn, account_id)
                if not token:
                    continue
                body = (
                    "<p>The daily RAG email agent pipeline failed.</p>"
                    f"<pre>{tb_str}</pre>"
                )
                send_mail(token, account_id, "RAG email agent - pipeline FAILED", body)
                logger.info("failure notification sent via %s", account_id)
                return
            logger.warning("no account had a usable token for failure notification")
        finally:
            conn.close()
    except Exception:
        logger.exception("failure notification itself failed")


def handler(event, context):
    logger.info("pipeline start")
    try:
        logger.info("phase: ingest")
        run_ingest()
        logger.info("phase: triage")
        run_triage()
        logger.info("phase: digest")
        run_digest()
    except Exception:
        tb_str = traceback.format_exc()
        logger.error("pipeline failed\n%s", tb_str)
        _notify_failure(tb_str)
        raise
    logger.info("pipeline complete")
    return {"status": "ok"}
