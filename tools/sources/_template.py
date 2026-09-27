"""
TEMPLATE for a new data source. Copy this file, rename it (e.g. strava.py),
and replace every TODO. Then register it in tools/sources/__init__.py and
add it to config.example.yaml. CONTRIBUTING.md has the full checklist.

Keep the "fetch" part deterministic and boring: call the API, return plain
Python data (dicts/lists). Claude does the thinking later, from format().
"""

import requests

import config
from sources.base import DataSource


class ExampleSource(DataSource):
    name = "example"                # TODO: the key under `sources:` in config.yaml
    title = "Example"               # TODO: human-friendly name
    description = "TODO: one line on what this adds to the brief."
    env_vars = ["EXAMPLE_API_KEY"]  # TODO: secrets it needs from .env ([] if none)
    fix_hint = "python setup.py --check"

    def fetch(self, allow_browser=True):
        # TODO: call the real API. Raise an exception if it fails - the core
        # catches it, keeps the rest of the brief, and tells the user.
        resp = requests.get(
            "https://api.example.com/today",
            headers={"Authorization": f"Bearer {config.env('EXAMPLE_API_KEY')}"},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    def demo(self):
        # TODO: realistic-but-fake data in exactly the same shape as fetch().
        return {"items": ["something interesting", "something else"]}

    def format(self, data):
        # TODO: plain text Claude will read. Start with a "--- Title ---" line.
        lines = [f"--- {self.title} (today) ---"]
        for item in data.get("items", []):
            lines.append(f"- {item}")
        return "\n".join(lines)

    # Optional: settings from config.yaml are in self.settings, e.g.
    #   limit = self.settings.get("limit", 5)
    #
    # Optional: dashboard numbers. Store one dict per day under your own key:
    #   def collect(self, store, log):
    #       import metrics_store
    #       metrics_store.merge_day(store, metrics_store.today_str(), "example", {"count": 3})
    #       log("example: stored today's count")
