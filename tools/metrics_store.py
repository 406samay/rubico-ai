"""
Day-indexed history of every metric the dashboard shows.

Stored in the local SQLite database (see db.py), one row per date
(YYYY-MM-DD). Each collection run merges into the existing day rather than
overwriting it, so a partial run (e.g. Monzo up, Spotify down) never wipes
data that's already there.

Shape:
{
  "meta": {"last_updated": iso8601, "currency": "GBP"},
  "days": {
    "2026-08-24": {
      "listening": {"tracks": .., "minutes": .., "by_artist": {..}, ...},
      "weather":   {"high_c": .., "low_c": .., "precipitation_mm": .., "description": ..},
      "spend":     {"total": .., "count": .., "transactions": [{name, amount}, ..]},
      "balance":   35.71
    }
  }
}
"""

import datetime
import json

import config
import db


def _empty():
    return {"meta": {"last_updated": None, "currency": config.get()["currency"]}, "days": {}}


def load():
    """The whole history as {"meta": {...}, "days": {date: {...}}} - the same
    shape the dashboard reads from /api/metrics."""
    data = _empty()
    data["meta"].update(db.kv_get("metrics_meta", {}) or {})
    with db.connect() as conn:
        for row in conn.execute("SELECT date, data FROM metrics_days"):
            try:
                data["days"][row["date"]] = json.loads(row["data"])
            except json.JSONDecodeError:
                continue  # one bad row shouldn't take the dashboard down
    return data


def save(data):
    """Writes every day in one transaction - all or nothing."""
    data.setdefault("meta", {})["last_updated"] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()
    with db.connect() as conn:
        conn.executemany(
            "INSERT INTO metrics_days (date, data) VALUES (?, ?) "
            "ON CONFLICT(date) DO UPDATE SET data = excluded.data",
            [(d, json.dumps(v, sort_keys=True)) for d, v in data["days"].items()],
        )
    db.kv_set("metrics_meta", data["meta"])


def merge_day(data, date_str, section, values):
    """Merge `values` into data['days'][date_str][section] without dropping
    keys that are already present and absent from `values`."""
    if not values:
        return data
    day = data["days"].setdefault(date_str, {})
    existing = day.get(section)
    if isinstance(existing, dict) and isinstance(values, dict):
        existing.update({k: v for k, v in values.items() if v is not None})
    else:
        day[section] = values
    return data


def set_day_value(data, date_str, key, value):
    if value is None:
        return data
    data["days"].setdefault(date_str, {})[key] = value
    return data


def local_date(iso_timestamp):
    """Bucket a UTC timestamp into the LOCAL calendar day.

    Every upstream API reports UTC. Bucketing on the raw string puts anything
    after 23:00 local during summer time onto the previous day - a track played at
    00:30 on Tuesday would be filed under Monday. Convert first, then slice.
    """
    if not iso_timestamp:
        return None
    text = iso_timestamp.replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(text)
    except ValueError:
        # Tolerate unusual fractional-second precision by trimming it.
        head, _, tail = text.partition(".")
        offset = tail[tail.find("+"):] if "+" in tail else (tail[tail.find("-"):] if "-" in tail else "")
        try:
            dt = datetime.datetime.fromisoformat(head + offset)
        except ValueError:
            return iso_timestamp[:10]

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    return dt.astimezone(config.tz()).date().isoformat()


def today():
    """Today in YOUR timezone (config.yaml), not the server's clock."""
    return datetime.datetime.now(config.tz()).date()


def today_str():
    return today().isoformat()


def date_range(days_back, end_date=None):
    """Yields YYYY-MM-DD strings from oldest to newest, inclusive of today."""
    end = end_date or today()
    for offset in range(days_back, -1, -1):
        yield (end - datetime.timedelta(days=offset)).isoformat()
