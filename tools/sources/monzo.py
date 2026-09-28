"""
Monzo (UK bank): balance and recent transactions, refreshing the access
token automatically when it's close to expiring.

Needs your own Monzo developer client (https://developers.monzo.com) -
the Monzo card on the /setup page walks you through it.
"""

import datetime
import json
import os
import random

import requests

import config
import metrics_store
from sources.base import DataSource


def _client():
    return config.env("MONZO_CLIENT_ID"), config.env("MONZO_CLIENT_SECRET")


def token_file():
    return config.token_path("monzo.json")



def _load_tokens():
    with open(token_file(), encoding="utf-8") as f:
        return json.load(f)


def _save_tokens(tokens):
    tokens["obtained_at"] = datetime.datetime.now().isoformat()
    with open(token_file(), "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)
    try:
        os.chmod(token_file(), 0o600)
    except OSError:
        pass


def _refresh(tokens):
    client_id, client_secret = _client()
    resp = requests.post("https://api.monzo.com/oauth2/token", data={
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": tokens["refresh_token"],
    })
    resp.raise_for_status()
    new_tokens = resp.json()
    _save_tokens(new_tokens)
    return new_tokens


def get_access_token():
    tokens = _load_tokens()

    obtained_at = tokens.get("obtained_at")
    if obtained_at:
        expires_at = datetime.datetime.fromisoformat(obtained_at) + datetime.timedelta(
            seconds=tokens["expires_in"]
        )
        if datetime.datetime.now() < expires_at - datetime.timedelta(minutes=10):
            return tokens["access_token"]

    tokens = _refresh(tokens)
    return tokens["access_token"]


def _headers():
    return {"Authorization": f"Bearer {get_access_token()}"}


def get_account_id():
    resp = requests.get("https://api.monzo.com/accounts", headers=_headers())
    resp.raise_for_status()
    accounts = [a for a in resp.json()["accounts"] if not a["closed"]]
    return accounts[0]["id"]


def get_balance(account_id):
    resp = requests.get(
        "https://api.monzo.com/balance", headers=_headers(), params={"account_id": account_id}
    )
    resp.raise_for_status()
    return resp.json()


def get_recent_transactions(account_id, days=1):
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
    resp = requests.get(
        "https://api.monzo.com/transactions", headers=_headers(),
        params={"account_id": account_id, "since": since, "expand[]": "merchant"},
    )
    if resp.status_code == 403 and "verification_required" in resp.text:
        raise MonzoVerificationRequired(
            "Monzo needs re-approval in the phone app before transaction "
            "history can be read again."
        )
    resp.raise_for_status()

    transactions = []
    for t in resp.json().get("transactions", []):
        if t["amount"] == 0 or t.get("decline_reason"):
            continue
        merchant = t.get("merchant")
        name = merchant.get("name") if isinstance(merchant, dict) else t.get("description", "Unknown")
        transactions.append({
            "created": t["created"],
            "amount": t["amount"] / 100,
            "currency": t["currency"],
            "name": name or "Unknown",
        })
    return transactions


class MonzoVerificationRequired(Exception):
    """Monzo refuses any transaction query that reaches back 90 days or more,
    returning 403 'forbidden.verification_required'. Measured empirically:
    89 days works, 90 does not. Balance is unaffected either way.

    Callers should therefore keep their window under 90 days rather than
    treating this as an auth failure. Raised (not swallowed) so a genuine
    occurrence is reported plainly instead of looking like a real run of
    zero-spending days."""


def get_transactions_range(account_id, days_back=90, page_size=100):
    """Pulls transactions over a longer window, paginating so nothing past the
    first page is silently dropped."""
    since = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_back)
    ).isoformat()

    collected = []
    seen_ids = set()
    cursor = since

    while True:
        try:
            resp = requests.get(
                "https://api.monzo.com/transactions",
                headers=_headers(),
                params={
                    "account_id": account_id,
                    "since": cursor,
                    "limit": page_size,
                    "expand[]": "merchant",
                },
                timeout=30,
            )
            resp.raise_for_status()
        except requests.HTTPError:
            if resp.status_code == 403 and "verification_required" in resp.text:
                raise MonzoVerificationRequired(
                    "Monzo needs re-approval in the phone app before transaction "
                    "history can be read again."
                )
            break

        page = resp.json().get("transactions", [])
        fresh = [t for t in page if t["id"] not in seen_ids]
        if not fresh:
            break

        for t in fresh:
            seen_ids.add(t["id"])
            collected.append(t)

        if len(page) < page_size:
            break
        cursor = fresh[-1]["id"]

    return collected


def _is_internal(name, category, owner_name):
    """Money moved between your own accounts is not expenditure.

    Deliberately keyed on the counterparty NAME, not the category. Monzo
    files genuine transfers from other people (e.g. money from a parent)
    under 'transfers' too, so treating that category as internal would
    wrongly erase real income. Name-matching is narrower but only fires on
    money that is provably going to or from yourself.
    """
    if category == "savings":  # pot transfers are unambiguously internal
        return True
    lowered = (name or "").strip().lower()
    if lowered in ("myself", "me"):
        return True
    if owner_name and lowered == owner_name.strip().lower():
        return True
    return False


def summarise_transactions_by_day(raw_transactions, owner_name=None):
    """Groups raw Monzo transactions into {date_str: {...}}.

    'total' is real outgoing spending as a positive number, with internal
    transfers pulled out into their own field so the headline figure means
    what it says. Nothing is dropped - every transaction still appears in
    'transactions', tagged so the UI can show it honestly.
    """
    by_day = {}
    for t in raw_transactions:
        if t.get("decline_reason") or t["amount"] == 0:
            continue

        # Bucket on the LOCAL day: Monzo timestamps are UTC, so a late-evening
        # purchase during BST would otherwise be filed under the day before.
        date_str = metrics_store.local_date(t["created"]) or t["created"][:10]
        merchant = t.get("merchant")
        name = merchant.get("name") if isinstance(merchant, dict) else None
        name = name or t.get("description") or "Unknown"
        category = t.get("category") or "general"
        amount = t["amount"] / 100
        internal = _is_internal(name, category, owner_name)

        day = by_day.setdefault(
            date_str,
            {
                "total": 0.0,
                "income": 0.0,
                "transfers_out": 0.0,
                "transfers_in": 0.0,
                "count": 0,
                "by_category": {},
                "transactions": [],
            },
        )

        if amount < 0:
            magnitude = -amount
            if internal:
                day["transfers_out"] = round(day["transfers_out"] + magnitude, 2)
            else:
                day["total"] = round(day["total"] + magnitude, 2)
                day["count"] += 1
                day["by_category"][category] = round(
                    day["by_category"].get(category, 0.0) + magnitude, 2
                )
        else:
            if internal:
                day["transfers_in"] = round(day["transfers_in"] + amount, 2)
            else:
                day["income"] = round(day["income"] + amount, 2)

        day["transactions"].append(
            {
                "name": name,
                "amount": amount,
                "category": category,
                "created": t["created"],
                "internal": internal,
            }
        )

    for day in by_day.values():
        day["transactions"].sort(key=lambda x: x["created"])
    return by_day


def get_owner_name(account_id=None):
    resp = requests.get("https://api.monzo.com/accounts", headers=_headers())
    resp.raise_for_status()
    for account in resp.json()["accounts"]:
        if account_id and account["id"] != account_id:
            continue
        for owner in account.get("owners") or []:
            if owner.get("preferred_name"):
                return owner["preferred_name"]
    return None


def get_spend_history(days_back=90):
    account_id = get_account_id()
    owner_name = get_owner_name(account_id)
    raw = get_transactions_range(account_id, days_back=days_back)
    return summarise_transactions_by_day(raw, owner_name=owner_name)


def get_summary(days=1):
    account_id = get_account_id()
    balance = get_balance(account_id)
    try:
        transactions = get_recent_transactions(account_id, days=days)
        blocked = False
    except MonzoVerificationRequired:
        transactions = []
        blocked = True
    return {
        "balance": balance["balance"] / 100,
        "currency": balance["currency"],
        "spend_today": balance["spend_today"] / 100,
        "transactions": transactions,
        "blocked": blocked,
    }


def format_summary(summary):
    lines = ["--- Monzo (bank account) ---"]
    lines.append(f"Balance: {summary['balance']:.2f} {summary['currency']}")
    lines.append(f"Spent today: {summary['spend_today']:.2f} {summary['currency']}")

    if summary["transactions"]:
        lines.append("Recent transactions:")
        for t in summary["transactions"]:
            # Spell out the direction. A bare signed number reads as ambiguous
            # and has already been misreported as money going the wrong way.
            if t["amount"] < 0:
                lines.append(
                    f"  {t['created']}: PAID OUT {abs(t['amount']):.2f} {t['currency']} to {t['name']}"
                )
            else:
                lines.append(
                    f"  {t['created']}: RECEIVED {t['amount']:.2f} {t['currency']} from {t['name']}"
                )
    elif summary.get("blocked"):
        lines.append(
            "Recent transactions unavailable: Monzo needs re-approval in the phone "
            "app before transaction history can be read. Balance above is still live."
        )
    else:
        lines.append("No recent transactions.")

    return "\n".join(lines)


# ---------------------------------------------------------------- plug-in

DEMO_MERCHANTS = [
    ("Pret A Manger", "eating_out", 4.2, 7.5), ("Tesco", "groceries", 8, 42),
    ("TfL", "transport", 2.8, 8.4), ("Spotify", "entertainment", 11.99, 11.99),
    ("Boots", "shopping", 3.5, 15), ("Deliveroo", "eating_out", 14, 26),
    ("Waterstones", "shopping", 9, 18), ("Shell", "transport", 35, 55),
]


class MonzoSource(DataSource):
    name = "monzo"
    title = "Monzo"
    description = "Bank balance and yesterday's spending (UK Monzo accounts only)."
    env_vars = ["MONZO_CLIENT_ID", "MONZO_CLIENT_SECRET"]
    setup_card = "monzo"

    def problems(self):
        issues = super().problems()
        if not token_file().exists():
            issues.append("not connected yet (use the Monzo card on the /setup page)")
        return issues

    def fetch(self):
        return get_summary(days=1)

    def demo(self):
        return {
            "balance": 1284.37, "currency": config.get()["currency"], "spend_today": 12.60,
            "blocked": False,
            "transactions": [
                {"created": "yesterday 08:12", "amount": -4.60, "currency": config.get()["currency"], "name": "Pret A Manger"},
                {"created": "yesterday 13:40", "amount": -8.00, "currency": config.get()["currency"], "name": "TfL"},
                {"created": "yesterday 17:05", "amount": 250.00, "currency": config.get()["currency"], "name": "Jordan Lee"},
            ],
        }

    def format(self, data):
        return format_summary(data)

    def collect(self, store, log):
        """Balance first: it keeps working even when transaction history is
        blocked, so a locked-out history must not cost us the balance too."""
        account_id = get_account_id()
        balance = get_balance(account_id)
        metrics_store.set_day_value(store, metrics_store.today_str(), "balance", balance["balance"] / 100)
        meta = store.setdefault("meta", {})
        meta["currency"] = balance["currency"]
        log(f"monzo: balance {balance['balance'] / 100:.2f} {balance['currency']}")

        try:
            # Monzo hard-refuses any transaction query reaching back 90 days or
            # more (403 forbidden.verification_required); 89 works. The default
            # of 85 leaves margin so a long run can't drift over the line.
            history = get_spend_history(int(self.settings.get("window_days", 85)))
        except MonzoVerificationRequired as exc:
            # Leave previously collected spending untouched - it is still true,
            # just no longer refreshable until the app is re-approved.
            meta["spend_blocked"] = True
            meta["spend_blocked_reason"] = str(exc)
            log(f"monzo: transaction history LOCKED - {exc}")
            return

        for date_str, spend in history.items():
            metrics_store.merge_day(store, date_str, "spend", spend)
        meta["spend_blocked"] = False
        meta.pop("spend_blocked_reason", None)
        meta["spend_last_success"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log(f"monzo: {len(history)} days with activity")

    def demo_history(self, dates):
        rng = random.Random(11)
        out = {}
        balance = 1284.37
        for date_str in reversed(dates):
            txs = []
            for _ in range(rng.randint(0, 4)):
                name, cat, lo, hi = rng.choice(DEMO_MERCHANTS)
                hour = rng.randint(8, 21)
                txs.append({"name": name, "amount": -round(rng.uniform(lo, hi), 2), "category": cat,
                            "created": f"{date_str}T{hour:02d}:{rng.randint(0, 59):02d}:00Z",
                            "internal": False})
            txs.sort(key=lambda t: t["created"])
            by_cat = {}
            for t in txs:
                by_cat[t["category"]] = round(by_cat.get(t["category"], 0) - t["amount"], 2)
            total = round(-sum(t["amount"] for t in txs), 2)
            out[date_str] = {"spend": {"total": total, "income": 0.0, "transfers_out": 0.0,
                                       "transfers_in": 0.0, "count": len(txs),
                                       "by_category": by_cat, "transactions": txs},
                             "balance": round(balance, 2)}
            balance += total
        return out
