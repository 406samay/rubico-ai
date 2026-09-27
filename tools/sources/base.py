"""
The shape every data source follows.

A data source is one thing Rubico can read from - Gmail, your bank, the
weather. Each one lives in its own file in tools/sources/ and fills in the
methods below. To add a new one, copy tools/sources/_template.py
(CONTRIBUTING.md walks through it).

The core only ever calls these methods, so it never needs to know the
details of any particular service:

  fetch()         real data for today's brief (raise if something's wrong)
  demo()          fake data in the SAME shape, for demo mode
  format(data)    turn that data into plain text for Claude to read
  problems()      what's missing before it can run (keys, logins) - for setup
  collect(...)    optional: store daily numbers for the dashboard charts
  demo_history()  optional: fake dashboard numbers for demo mode
"""

import config


class DataSource:
    name = ""            # key under `sources:` in config.yaml, e.g. "weather"
    title = ""           # human name, e.g. "Weather"
    description = ""     # one line shown in setup.py
    env_vars = []        # .env keys this source needs, e.g. ["MONZO_CLIENT_ID"]
    fix_hint = ""        # what to run when it breaks, e.g. "python setup.py --only monzo"

    @property
    def settings(self):
        return config.source(self.name)

    @property
    def enabled(self):
        return bool(self.settings.get("enabled"))

    # ---- required -------------------------------------------------------

    def fetch(self, allow_browser=True):
        raise NotImplementedError

    def demo(self):
        raise NotImplementedError

    def format(self, data):
        raise NotImplementedError

    # ---- optional -------------------------------------------------------

    def problems(self):
        """Things stopping this source from working. Empty list = ready."""
        return [f"{var} is missing from .env" for var in self.env_vars if not config.env(var)]

    def broken_parts(self, data):
        """For sources with several accounts: which ones failed, e.g. ["Gmail work"]."""
        return []

    def collect(self, store, log):
        """Merge real day-by-day numbers into the dashboard store. Optional."""

    def demo_history(self, dates):
        """Fake {date: {section: values}} for the dashboard in demo mode. Optional."""
        return {}
