"""
Gmail: the last 24 hours of email from each account in
sources.gmail.accounts, so the brief can flag what needs a reply.

Actions (send a reply, trash emails) live in tools/gmail_actions.py and
always go through a cancel window first.
"""

from googleapiclient.discovery import build

from google_auth import client_config, get_credentials, token_file
from sources.base import DataSource


def gmail_service(label, allow_browser=True):
    creds = get_credentials(label, allow_browser=allow_browser)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def get_recent_emails(label, max_results=10, allow_browser=True):
    service = gmail_service(label, allow_browser)

    results = service.users().messages().list(
        userId="me", maxResults=max_results, q="newer_than:1d"
    ).execute()
    messages = results.get("messages", [])

    emails = []
    for msg in messages:
        full = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["Subject", "From"],
        ).execute()
        headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
        emails.append({
            "id": msg["id"],
            "from": headers.get("From", "(unknown)"),
            "subject": headers.get("Subject", "(no subject)"),
            "snippet": full.get("snippet", ""),
        })
    return emails


# Realistic-but-fake inbox for demo mode. Also used by gmail_actions in demo.
DEMO_INBOX = {
    "personal": [
        ("Jordan Lee <jordan.lee@example.com>", "Dinner Saturday?",
         "Hey! Are you still up for dinner on Saturday? I booked 7:30 at the Italian place, let me know"),
        ("Northside Dental <reminders@northside-dental.example>", "Appointment reminder",
         "This is a reminder of your check-up on Thursday at 10:15. Reply C to confirm"),
        ("Parcel Tracking <no-reply@parcels.example>", "Your parcel is out for delivery",
         "Your order #48213 will arrive today between 1pm and 3pm"),
        ("Bank Security <security@bank.example>", "New sign-in to your account",
         "We noticed a new sign-in from Chrome on Windows. If this was you, no action is needed"),
        ("MegaStore <deals@megastore.example>", "48 hours only: 30% off everything",
         "Our biggest sale of the season ends Sunday at midnight"),
    ],
    "work": [
        ("Priya Shah <priya@acme.example>", "Q3 report - need your numbers by Wed",
         "Hi, could you send over the regional figures by Wednesday EOD so I can finalise the deck?"),
        ("Calendar <calendar@acme.example>", "Updated invitation: Sprint review",
         "Sprint review has moved to 3:00pm today"),
        ("IT Helpdesk <it@acme.example>", "Password expires in 3 days",
         "Your network password expires in 3 days. Change it from the portal to avoid being locked out"),
    ],
}


def demo_emails(label):
    return [
        {"id": f"demo-{label}-{i}", "from": sender, "subject": subject, "snippet": snippet}
        for i, (sender, subject, snippet) in enumerate(DEMO_INBOX.get(label, []))
    ]


class GmailSource(DataSource):
    name = "gmail"
    title = "Gmail"
    description = "Your last 24h of email - flags what needs a reply; lets you reply/delete by chat."
    fix_hint = "python tools/reauth_google.py"

    def fix_command(self):
        cmd = super().fix_command()
        return cmd.replace("#gmail", "#google")

    @property
    def accounts(self):
        return self.settings.get("accounts") or []

    def problems(self):
        issues = []
        if not client_config():
            issues.append("Google OAuth client not set (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)")
        if not self.accounts:
            issues.append("no accounts listed under sources.gmail.accounts")
        for label in self.accounts:
            if not token_file(label).exists():
                issues.append(f"'{label}' hasn't logged in yet")
        return issues

    def fetch(self, allow_browser=True):
        max_results = int(self.settings.get("max_emails", 10))
        out = {}
        for label in self.accounts:
            try:
                out[label] = get_recent_emails(label, max_results, allow_browser)
            except Exception as e:  # one dead account mustn't hide the others
                out[label] = e
        return out

    def demo(self):
        return {label: demo_emails(label) for label in self.accounts}

    def broken_parts(self, data):
        return [f"Gmail {label}" for label, v in data.items() if isinstance(v, Exception)]

    def format(self, data):
        lines = []
        for label, emails in data.items():
            lines.append(f"--- Emails from {label} (last 24h) ---")
            if isinstance(emails, Exception):
                lines.append(f"(unavailable: {emails})")
            elif not emails:
                lines.append("(no new emails)")
            else:
                for e in emails:
                    lines.append(f"ID: {e['id']} (account: {label})")
                    lines.append(f"From: {e['from']}")
                    lines.append(f"Subject: {e['subject']}")
                    lines.append(f"Preview: {e['snippet']}")
                    lines.append("")
            lines.append("")
        return "\n".join(lines).rstrip()
