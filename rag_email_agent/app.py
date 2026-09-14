from flask import Flask, jsonify, redirect, session, url_for

import config
from auth.accounts import get_token_for_account
from auth.routes import bp as auth_bp
from graph.client import get_recent_messages
from ingest.db import get_connection


def create_app():
    app = Flask(__name__)
    app.secret_key = config.FLASK_SECRET_KEY
    app.register_blueprint(auth_bp)

    @app.route("/")
    def fetch_messages():
        if not (account_id := session.get("account_id")):
            return redirect(url_for("auth.login"))

        conn = get_connection()
        try:
            token = get_token_for_account(conn, account_id)
        finally:
            conn.close()

        if not token:
            return redirect(url_for("auth.login"))
        return jsonify(get_recent_messages(token))

    return app


if __name__ == "__main__":
    create_app().run(port=5000, debug=True)
