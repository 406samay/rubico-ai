"""
Pulls today's weather forecast from Open-Meteo (free, no API key needed).
"""

import random

import requests

import config
from sources.base import DataSource

# WMO weather codes -> plain English
WEATHER_CODES = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow",
    80: "light rain showers", 81: "rain showers", 82: "heavy rain showers",
    95: "thunderstorm", 96: "thunderstorm with hail",
}


DAILY_FIELDS = "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode"


def _fetch_daily(past_days=0, forecast_days=1):
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": config.get()["location"]["latitude"],
            "longitude": config.get()["location"]["longitude"],
            "daily": DAILY_FIELDS,
            "timezone": config.get()["timezone"],
            "past_days": past_days,
            "forecast_days": forecast_days,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["daily"]


def _row(daily, i):
    code = daily["weathercode"][i]
    return {
        "high_c": daily["temperature_2m_max"][i],
        "low_c": daily["temperature_2m_min"][i],
        "precipitation_mm": daily["precipitation_sum"][i],
        "code": code,
        "description": WEATHER_CODES.get(code, "unknown conditions"),
    }


def get_today_weather():
    daily = _fetch_daily(past_days=0, forecast_days=1)
    return _row(daily, 0)


def get_weather_history(days_back=90):
    """Returns {date_str: weather_dict} covering the past `days_back` days
    plus today. Open-Meteo caps past_days at 92, and the oldest rows can come
    back null when they fall outside archive coverage - those are dropped so
    they never land in the store as fake zero-degree days."""
    daily = _fetch_daily(past_days=min(days_back, 92), forecast_days=1)
    out = {}
    for i, date in enumerate(daily["time"]):
        row = _row(daily, i)
        if row["high_c"] is None:
            continue
        out[date] = row
    return out


def format_weather_summary(weather):
    lines = [f"--- Weather in {config.get()['location']['name']} (today) ---"]
    lines.append(
        f"{weather['description'].capitalize()}, high {weather['high_c']}C / low {weather['low_c']}C, "
        f"{weather['precipitation_mm']}mm precipitation expected"
    )
    return "\n".join(lines)


def _demo_day(rng):
    code = rng.choice([0, 1, 2, 3, 3, 61, 63, 80])
    high = round(rng.uniform(13, 22), 1)
    return {
        "high_c": high,
        "low_c": round(high - rng.uniform(5, 9), 1),
        "precipitation_mm": round(rng.uniform(0.5, 9), 1) if code >= 61 else 0.0,
        "code": code,
        "description": WEATHER_CODES.get(code, "unknown conditions"),
    }


class WeatherSource(DataSource):
    name = "weather"
    title = "Weather"
    description = "Today's forecast for your city (Open-Meteo - free, no key needed)."

    def fetch(self, allow_browser=True):
        return get_today_weather()

    def demo(self):
        return {"high_c": 18.4, "low_c": 11.2, "precipitation_mm": 3.1, "code": 80,
                "description": "light rain showers"}

    def format(self, data):
        return format_weather_summary(data)

    def collect(self, store, log):
        import metrics_store

        history = get_weather_history(90)
        for date_str, weather in history.items():
            metrics_store.merge_day(store, date_str, "weather", weather)
        log(f"weather: {len(history)} days")

    def demo_history(self, dates):
        rng = random.Random(7)
        out = {d: {"weather": _demo_day(rng)} for d in dates}
        if dates:
            out[dates[-1]] = {"weather": self.demo()}
        return out
