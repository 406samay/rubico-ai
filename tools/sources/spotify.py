"""
Pulls listening data from Spotify.

An important limit shapes this module: Spotify's recently-played endpoint
returns at most the last 50 plays and has no deep-history equivalent. There
is no way to backfill months the way Monzo or Open-Meteo allow - listening
history has to be *accumulated* by polling often enough that 50 plays never
elapse between runs (roughly 3 hours of continuous listening).

So the collector polls hourly (metrics.collect_every_minutes) and unions
new plays into the store. Anything
before the day Spotify was connected simply does not exist, and the dashboard
says so rather than implying a quiet month.
"""

import datetime
import json
import os
import random

import requests

import config
import metrics_store
from sources.base import DataSource

API = "https://api.spotify.com/v1"


def token_file():
    return config.token_path("spotify.json")


def _load_tokens():
    with open(token_file(), encoding="utf-8") as f:
        return json.load(f)


def _save_tokens(tokens):
    tokens["obtained_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(token_file(), "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)
    try:
        os.chmod(token_file(), 0o600)
    except OSError:
        pass


def _refresh(tokens):
    # PKCE refresh: client_id in the body, no Basic auth header, no secret.
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": config.env("SPOTIFY_CLIENT_ID"),
        },
        timeout=30,
    )
    resp.raise_for_status()
    fresh = resp.json()
    # Spotify often omits a new refresh_token; keep the existing one so the
    # next refresh doesn't fail with a missing key.
    fresh.setdefault("refresh_token", tokens["refresh_token"])
    _save_tokens(fresh)
    return fresh


def get_access_token():
    tokens = _load_tokens()
    obtained_at = tokens.get("obtained_at")
    if obtained_at:
        expires_at = datetime.datetime.fromisoformat(obtained_at) + datetime.timedelta(
            seconds=tokens.get("expires_in", 3600)
        )
        if datetime.datetime.now(datetime.timezone.utc) < expires_at - datetime.timedelta(minutes=5):
            return tokens["access_token"]
    return _refresh(tokens)["access_token"]


def _headers():
    return {"Authorization": f"Bearer {get_access_token()}"}


def _artists(track):
    return [a["name"] for a in track.get("artists", []) if a.get("name")]


def get_recently_played(after_ms=None, limit=50):
    """Most recent plays, newest first. `after_ms` is a Unix ms timestamp -
    passing the last play we already stored avoids re-fetching everything."""
    params = {"limit": min(limit, 50)}
    if after_ms:
        params["after"] = int(after_ms)

    resp = requests.get(f"{API}/me/player/recently-played", headers=_headers(), params=params, timeout=30)
    if resp.status_code == 204:
        return []
    resp.raise_for_status()

    plays = []
    for item in resp.json().get("items", []):
        track = item.get("track") or {}
        if not track.get("name"):
            continue
        plays.append({
            "played_at": item["played_at"],
            "track": track["name"],
            "artist": ", ".join(_artists(track)) or "Unknown",
            "album": (track.get("album") or {}).get("name", ""),
            "ms": track.get("duration_ms", 0),
        })
    return plays


def get_top(kind="artists", time_range="short_term", limit=10):
    """kind: artists | tracks. time_range: short_term (~4wk),
    medium_term (~6mo), long_term (~1yr)."""
    resp = requests.get(
        f"{API}/me/top/{kind}",
        headers=_headers(),
        params={"time_range": time_range, "limit": limit},
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])

    out = []
    for item in items:
        if kind == "artists":
            out.append({"name": item.get("name", "Unknown"), "genres": item.get("genres", [])[:3]})
        else:
            out.append({
                "name": item.get("name", "Unknown"),
                "artist": ", ".join(_artists(item)) or "Unknown",
            })
    return out


def get_now_playing():
    resp = requests.get(f"{API}/me/player/currently-playing", headers=_headers(), timeout=20)
    if resp.status_code == 204 or not resp.content:
        return None
    resp.raise_for_status()
    data = resp.json()
    track = data.get("item") or {}
    if not track.get("name"):
        return None
    return {
        "track": track["name"],
        "artist": ", ".join(_artists(track)) or "Unknown",
        "is_playing": bool(data.get("is_playing")),
    }


def summarise_plays_by_day(plays):
    """Buckets plays into local calendar days with per-day aggregates.

    'minutes' sums full track durations. Spotify only reports a play once it
    passes ~30 seconds, but it does not say how much of the track was heard,
    so this slightly overstates time when tracks are skipped part-way.
    """
    by_day = {}
    for play in plays:
        date_str = metrics_store.local_date(play["played_at"])
        if not date_str:
            continue
        day = by_day.setdefault(
            date_str, {"plays": [], "tracks": 0, "minutes": 0.0, "by_artist": {}}
        )
        day["plays"].append(play)

    for date_str, day in by_day.items():
        # Deduplicate on played_at: overlapping polls will re-deliver plays.
        unique = {p["played_at"]: p for p in day["plays"]}
        ordered = sorted(unique.values(), key=lambda p: p["played_at"])
        day["plays"] = ordered
        day["tracks"] = len(ordered)
        day["minutes"] = round(sum(p.get("ms", 0) for p in ordered) / 60000, 1)

        artists = {}
        for p in ordered:
            artists[p["artist"]] = artists.get(p["artist"], 0) + 1
        day["by_artist"] = dict(sorted(artists.items(), key=lambda x: -x[1]))
        day["top_artist"] = next(iter(day["by_artist"]), None)
    return by_day


def merge_into_day(existing, incoming):
    """Union two days of listening, keyed on played_at, and recompute."""
    plays = {p["played_at"]: p for p in (existing or {}).get("plays", [])}
    plays.update({p["played_at"]: p for p in incoming.get("plays", [])})
    merged = summarise_plays_by_day(list(plays.values()))
    return next(iter(merged.values()), incoming)


def format_summary(day_record, now_playing=None, top_artists=None):
    lines = ["--- Spotify (today) ---"]
    if now_playing and now_playing.get("is_playing"):
        lines.append(f"Now playing: {now_playing['track']} - {now_playing['artist']}")

    if not day_record or not day_record.get("tracks"):
        # Spotify only records a play once the track finishes, so "now playing"
        # with nothing logged is normal, not a contradiction - say why.
        if now_playing and now_playing.get("is_playing"):
            lines.append(
                "No completed plays logged today yet (the track above is still "
                "playing; Spotify only records it once it finishes)."
            )
        else:
            lines.append("Nothing played yet today.")
    else:
        lines.append(
            f"{day_record['tracks']} tracks, about {day_record['minutes']:.0f} minutes"
        )
        top = list(day_record.get("by_artist", {}).items())[:3]
        if top:
            lines.append(
                "Most played: " + ", ".join(f"{name} ({count})" for name, count in top)
            )

    if top_artists:
        lines.append(
            "Top artists (last 4 weeks): " + ", ".join(a["name"] for a in top_artists[:5])
        )
    return "\n".join(lines)


# ---------------------------------------------------------------- plug-in

DEMO_ARTISTS = [
    ("Fred again..", ["Delilah (pull me out of this)", "Jungle", "Marea"]),
    ("Little Simz", ["Gorilla", "Venom", "Point and Kill"]),
    ("Khruangbin", ["Time (You and I)", "People Everywhere", "Maria Tambien"]),
    ("Arctic Monkeys", ["505", "Do I Wanna Know?", "Arabella"]),
    ("Nia Archives", ["Crowded Roomz", "So Tell Me"]),
]


class SpotifySource(DataSource):
    name = "spotify"
    title = "Spotify"
    description = "What you've been listening to (tracks, minutes, top artists)."
    env_vars = ["SPOTIFY_CLIENT_ID"]
    setup_card = "spotify"

    def problems(self):
        issues = super().problems()
        if not token_file().exists():
            issues.append("not connected yet (use the Spotify card on the /setup page)")
        return issues

    def fetch(self):
        """Yesterday + today, so a morning brief still has something to say."""
        by_day = summarise_plays_by_day(get_recently_played())
        yesterday = (metrics_store.today() - datetime.timedelta(days=1)).isoformat()
        try:
            top = get_top("artists", "short_term", limit=5)
        except Exception:
            top = None
        return {"day": by_day.get(yesterday), "label": "yesterday",
                "now_playing": get_now_playing(), "top_artists": top}

    def demo(self):
        plays = self._demo_plays(random.Random(3), metrics_store.today_str(), 14)
        return {"day": summarise_plays_by_day(plays).get(metrics_store.today_str()),
                "label": "yesterday", "now_playing": None,
                "top_artists": [{"name": a} for a, _ in DEMO_ARTISTS]}

    def format(self, data):
        text = format_summary(data.get("day"), data.get("now_playing"), data.get("top_artists"))
        return text.replace("(today)", f"({data.get('label', 'today')})", 1)

    def collect(self, store, log):
        """Spotify can't be backfilled - only the last 50 plays are reachable -
        so every run unions whatever is new into the days already stored."""
        plays = get_recently_played()
        by_day = summarise_plays_by_day(plays)

        for date_str, day in by_day.items():
            existing = store["days"].get(date_str, {}).get("listening")
            store["days"].setdefault(date_str, {})["listening"] = merge_into_day(existing, day)
        log(f"spotify: {len(plays)} plays fetched across {len(by_day)} day(s)")

        meta = store.setdefault("meta", {})
        try:
            meta["top_artists_4w"] = get_top("artists", "short_term", limit=8)
            meta["top_tracks_4w"] = get_top("tracks", "short_term", limit=8)
        except Exception as exc:
            log(f"spotify: top items unavailable ({type(exc).__name__})")

        # Earliest day we actually hold listening data for - not the day we
        # connected. The first poll reaches back through the last 50 plays, which
        # can already cover several days, and claiming tracking "started today"
        # would make the dashboard deny days it can plainly show.
        known = [d for d, r in store["days"].items() if r.get("listening", {}).get("tracks")]
        if known:
            earliest = min(known)
            current = meta.get("spotify_since")
            meta["spotify_since"] = min(current, earliest) if current else earliest

    @staticmethod
    def _demo_plays(rng, date_str, count):
        plays = []
        for i in range(count):
            artist, tracks = rng.choice(DEMO_ARTISTS)
            hour, minute = 7 + (i * 13) // 60 % 15, (i * 13) % 60
            plays.append({"played_at": f"{date_str}T{hour:02d}:{minute:02d}:{rng.randint(0, 59):02d}.000Z",
                          "track": rng.choice(tracks), "artist": artist, "album": "",
                          "ms": rng.randint(150_000, 260_000)})
        return plays

    def demo_history(self, dates):
        rng = random.Random(5)
        out = {}
        for date_str in dates:
            plays = self._demo_plays(rng, date_str, rng.choice([0, 6, 12, 18, 25, 32]))
            day = summarise_plays_by_day(plays).get(date_str)
            if day:
                out[date_str] = {"listening": day}
        return out
