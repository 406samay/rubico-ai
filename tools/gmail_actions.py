"""
Gmail actions that go beyond reading - drafting reply metadata and actually
sending. Sending is deliberately kept out of the request/response loop that
answers questions; it only happens via the pending-actions review window
(see pending_actions.py) so nothing goes out without a chance to cancel.

In demo mode every function here works on the fake inbox and never
touches a real account.
"""

import base64
from email.mime.text import MIMEText

import config
from sources.gmail import demo_emails, gmail_service


def get_reply_context(account_label, gmail_message_id):
    """Looks up what's needed to send a properly-threaded reply to a message."""
    if config.is_demo():
        match = next((e for e in demo_emails(account_label) if e["id"] == gmail_message_id), None)
        return {"thread_id": "demo-thread", "message_id_header": "",
                "subject": match["subject"] if match else "(demo)", "from": match["from"] if match else ""}
    service = gmail_service(account_label)

    full = service.users().messages().get(
        userId="me", id=gmail_message_id, format="metadata",
        metadataHeaders=["Message-ID", "Subject", "From"],
    ).execute()
    headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}

    return {
        "thread_id": full["threadId"],
        "message_id_header": headers.get("Message-ID", ""),
        "subject": headers.get("Subject", "(no subject)"),
        "from": headers.get("From", ""),
    }


def send_reply(account_label, to, subject, thread_id, in_reply_to_header, body):
    if config.is_demo():
        print(f"(demo) would send reply to {to}")
        return {"id": "demo"}
    service = gmail_service(account_label)

    mime_msg = MIMEText(body)
    mime_msg["To"] = to
    mime_msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if in_reply_to_header:
        mime_msg["In-Reply-To"] = in_reply_to_header
        mime_msg["References"] = in_reply_to_header

    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
    return service.users().messages().send(
        userId="me", body={"raw": raw, "threadId": thread_id}
    ).execute()


def list_promotional_emails(account_label, max_results=200):
    """Uses Gmail's own Promotions-tab classification, not a guess."""
    if config.is_demo():
        return [e for e in demo_emails(account_label) if "deals@" in e["from"]]
    service = gmail_service(account_label)

    results = service.users().messages().list(
        userId="me", labelIds=["CATEGORY_PROMOTIONS"], maxResults=max_results
    ).execute()
    messages = results.get("messages", [])

    previews = []
    for msg in messages:
        full = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["Subject", "From"],
        ).execute()
        headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
        previews.append({
            "id": msg["id"],
            "from": headers.get("From", "(unknown)"),
            "subject": headers.get("Subject", "(no subject)"),
        })
    return previews


def search_messages(account_label, query, max_results=50):
    """Free-form Gmail search (same syntax as the Gmail search bar), used to
    find messages matching a description like 'monzo login alerts'."""
    if config.is_demo():
        words = [w.strip('"()').lower() for w in query.replace(":", " ").split() if len(w) > 3]
        return [dict(e, date="") for e in demo_emails(account_label)
                if any(w in (e["from"] + e["subject"]).lower() for w in words)]
    service = gmail_service(account_label)

    results = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    messages = results.get("messages", [])

    previews = []
    for msg in messages:
        full = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["Subject", "From", "Date"],
        ).execute()
        headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
        previews.append({
            "id": msg["id"],
            "from": headers.get("From", "(unknown)"),
            "subject": headers.get("Subject", "(no subject)"),
            "date": headers.get("Date", ""),
        })
    return previews


def trash_messages(account_label, message_ids):
    if config.is_demo():
        print(f"(demo) would move {len(message_ids)} emails to Trash")
        return list(message_ids)
    service = gmail_service(account_label)

    trashed = []
    for message_id in message_ids:
        service.users().messages().trash(userId="me", id=message_id).execute()
        trashed.append(message_id)
    return trashed
