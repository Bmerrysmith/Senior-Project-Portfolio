import html

URGENCY_ORDER = ["urgent", "high", "medium", "low"]
URGENCY_LABELS = {"urgent": "Urgent", "high": "High", "medium": "Medium", "low": "Low"}


def build_digest_html(digest_date, summaries_by_urgency, unprocessed_emails=None):
    sections = []
    for level in URGENCY_ORDER:
        items = summaries_by_urgency.get(level, [])
        if not items:
            continue
        rows = "".join(
            f"<li><strong>{html.escape(item['subject'] or '(no subject)')}</strong> "
            f"— {html.escape(item['summary'])} "
            f"<span style=\"color:#666\">({html.escape(item['sender'] or '')})</span></li>"
            for item in items
        )
        sections.append(f"<h3>{URGENCY_LABELS[level]}</h3><ul>{rows}</ul>")

    note = ""
    if unprocessed_emails:
        note = (
            f"<p style=\"color:#b00\"><strong>Note:</strong> {len(unprocessed_emails)} "
            f"email(s) could not be processed today and are not reflected above. "
            f"They're listed below.</p>"
        )
        rows = "".join(
            f"<li><strong>{html.escape(item['subject'] or '(no subject)')}</strong> "
            f"<span style=\"color:#666\">({html.escape(item['sender'] or '')}, "
            f"{item['received_at']})</span></li>"
            for item in unprocessed_emails
        )
        sections.append(f"<h3>Unprocessed (not triaged)</h3><ul>{rows}</ul>")

    return f"<h2>Daily Digest — {digest_date.isoformat()}</h2>" + note + "".join(sections)
