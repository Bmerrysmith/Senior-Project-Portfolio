from bs4 import BeautifulSoup
from email_reply_parser import EmailReplyParser


def html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["style", "script"]):
        tag.decompose()
    return soup.get_text(separator=" ")


def strip_quoted(text):
    return EmailReplyParser.parse_reply(text).strip()
