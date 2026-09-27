"""
Pulls every metric the dashboard shows and merges it into the day-indexed
history store (the local database).

  python tools/collect_metrics.py

run.py calls this every metrics.collect_every_minutes (default hourly).
Each switched-on source that has a collect() method adds its own numbers;
each is isolated, so if one is down the others still land in the store.
"""

import datetime
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import metrics_store
import sources


def collect(log=print):
    started = datetime.datetime.now()
    data = metrics_store.load()
    before = len(data["days"])

    for src in sources.enabled_sources():
        if src.problems():
            log(f"{src.name}: not set up yet ({'; '.join(src.problems())})")
            continue
        try:
            src.collect(data, log)
        except Exception as exc:
            log(f"{src.name}: FAILED ({type(exc).__name__}: {exc})")

    metrics_store.save(data)
    elapsed = (datetime.datetime.now() - started).total_seconds()
    log(f"store: {len(data['days'])} days total (+{len(data['days']) - before} new) in {elapsed:.1f}s")


if __name__ == "__main__":
    collect()
