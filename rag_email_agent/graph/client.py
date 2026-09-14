import time

import requests

import config

SEND_MAX_RETRIES = 3
SEND_RETRY_BACKOFF_SECONDS = 2


def get_recent_messages(access_token, top=10):
    response = requests.get(
        f"{config.GRAPH_BASE_URL}/me/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "$top": top,
            "$select": "subject,from,receivedDateTime",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("value", [])


def send_mail(access_token, to_address, subject, html_body):
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": to_address}}],
        }
    }
    response = None
    for attempt in range(SEND_MAX_RETRIES):
        response = requests.post(
            f"{config.GRAPH_BASE_URL}/me/sendMail",
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
            timeout=30,
        )
        if response.ok:
            return
        if attempt < SEND_MAX_RETRIES - 1:
            time.sleep(SEND_RETRY_BACKOFF_SECONDS * (2**attempt))
    response.raise_for_status()


def get_messages_with_body(access_token, top=50):
    response = requests.get(
        f"{config.GRAPH_BASE_URL}/me/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "$top": top,
            "$select": "subject,from,receivedDateTime,body",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("value", [])
