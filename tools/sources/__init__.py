"""
Every data source Rubico knows about. To add a new one:
  1. copy _template.py to <yourname>.py and fill it in
  2. import it below and add it to ALL
  3. add a `<yourname>: {enabled: false}` block to config.example.yaml
See CONTRIBUTING.md for the full walkthrough.
"""

from sources.calendar import CalendarSource
from sources.gmail import GmailSource
from sources.monzo import MonzoSource
from sources.spotify import SpotifySource
from sources.weather import WeatherSource

# Order here = order the sections appear in the text Claude reads.
ALL = [GmailSource, CalendarSource, WeatherSource, MonzoSource, SpotifySource]


def all_sources():
    return [cls() for cls in ALL]


def enabled_sources():
    return [s for s in all_sources() if s.enabled]


def get(name):
    for s in all_sources():
        if s.name == name:
            return s
    raise KeyError(name)
