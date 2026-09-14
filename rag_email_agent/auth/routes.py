from flask import Blueprint, redirect, request, session, url_for

import config
from auth.accounts import is_approved, upsert_account
from auth.msal_client import build_msal_app
from ingest.db import get_connection

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/login")
def login():
    app = build_msal_app()
    flow = app.initiate_auth_code_flow(
        config.GRAPH_SCOPES,
        redirect_uri=config.REDIRECT_URI,
    )
    # MSAL's flow dict carries the PKCE code_verifier and state — it must
    # survive until the callback request, so it goes in the session rather
    # than being recomputed.
    session["auth_flow"] = flow
    return redirect(flow["auth_uri"])


@bp.route("/callback")
def callback():
    app = build_msal_app()
    flow = session.pop("auth_flow", {})
    result = app.acquire_token_by_auth_code_flow(flow, request.args)

    if "access_token" not in result:
        return f"Auth failed: {result.get('error_description', result)}", 400

    email = result["id_token_claims"]["preferred_username"]

    conn = get_connection()
    try:
        if not is_approved(conn, email):
            return "Womp Womp looks like this account is not approved to use this application. Better luck next time :(", 403

        if "refresh_token" in result:
            upsert_account(conn, email, result["refresh_token"])
    finally:
        conn.close()

    session["account_id"] = email
    return redirect(url_for("fetch_messages"))
