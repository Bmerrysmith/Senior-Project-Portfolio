import json
import time

import requests

import config

MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 2

BASE_SYSTEM_PROMPT = (
   "You are an email triage assistant for a single inbox. You will be given "
"an email to evaluate, some of the sender's past emails for context, and "
"some similar past emails to help judge whether this looks like a routine, "
"recurring pattern or something novel.\n\n"

"First, check the subject line. If it is a \"Daily Digest\" email (or a "
"clear variant of that title), do NOT summarize it. Instead respond with "
"exactly this JSON object and nothing else:\n"
"{\"summary\": \"Daily Digest, skipped\", \"urgency\": \"low\"}\n\n"

"Otherwise, evaluate the email normally:\n\n"

"SUMMARY: Write 1-3 sentences capturing what the email is actually asking "
"for or informing the user of. State the core action or information, not "
"the email's tone or pleasantries. If the email requires a response or "
"decision, say what kind.\n\n"

"URGENCY: Choose one of \"low\", \"medium\", \"high\", \"urgent\" using "
"these criteria:\n"
"- urgent: time-sensitive with real consequences if missed today (a "
"deadline within 24 hours, an outage, a person waiting on a blocking "
"decision)\n"
"- high: needs a response or action within a few days, or is from someone "
"whose emails historically require prompt attention\n"
"- medium: needs a response eventually but has no hard deadline\n"
"- low: informational, routine, or matches a recurring pattern with no "
"action needed (newsletters, automated notifications, FYI threads)\n\n"

"Use the sender's past emails to judge whether this sender's messages are "
"typically high-stakes or routine for this user. Use the similar past "
"emails to judge whether this is a recurring pattern (lean toward lower "
"urgency) or something novel (lean toward evaluating urgency on its own "
"merits).\n\n"

"Respond with a JSON object with exactly two fields: \"summary\" (a 1-3 "
"sentence summary) and \"urgency\" (one of \"low\", \"medium\", \"high\", "
"\"urgent\"). Do not include any other text, explanation, or markdown "
"formatting outside the JSON object."
)


def _build_system_prompt(priority_context):
    if not priority_context:
        return BASE_SYSTEM_PROMPT
    return (
        f"{BASE_SYSTEM_PROMPT}\n\n"
        f"Additional context for this account's priorities: {priority_context}"
    )


def _snippet(text):
    text = text or ""
    return text[: config.CONTEXT_SNIPPET_CHARS]


def _format_email_list(label, emails):
    if not emails:
        return f"{label}: none"
    lines = [f"{label}:"]
    for email in emails:
        lines.append(
            f"- [{email['received_at']}] {email['subject']}: {_snippet(email['raw_body'])}"
        )
    return "\n".join(lines)


def build_prompt(target, sender_context, grounding):
    return "\n\n".join(
        [
            f"Email to summarize:\nSubject: {target['subject']}\n"
            f"From: {target['sender']}\nReceived: {target['received_at']}\n"
            f"Body: {target['raw_body']}",
            _format_email_list("Past emails from this sender", sender_context),
            _format_email_list("Similar past emails", grounding),
        ]
    )


def _call_openai(payload):
    response = None
    for attempt in range(MAX_RETRIES):
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
            json=payload,
            timeout=60,
        )
        if response.ok:
            return response
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
    response.raise_for_status()


def summarize_and_grade(target, sender_context, grounding, priority_context):
    response = _call_openai(
        {
            "model": config.SUMMARIZATION_MODEL,
            "messages": [
                {"role": "system", "content": _build_system_prompt(priority_context)},
                {"role": "user", "content": build_prompt(target, sender_context, grounding)},
            ],
            "response_format": {"type": "json_object"},
        }
    )
    result = json.loads(response.json()["choices"][0]["message"]["content"])
    return result["summary"], result["urgency"]
