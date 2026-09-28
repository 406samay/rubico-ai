"""
Turns a city name into what Rubico needs: coordinates (for weather),
timezone and currency. Uses Open-Meteo's free geocoding - no key needed.
Used by the /setup page (tools/web_setup.py).
"""

import requests

# Country -> currency, so setup doesn't have to ask. Anything else: it asks.
CURRENCIES = {
    "GB": "GBP", "US": "USD", "CA": "CAD", "AU": "AUD", "NZ": "NZD", "IE": "EUR", "IN": "INR",
    "DE": "EUR", "FR": "EUR", "ES": "EUR", "IT": "EUR", "NL": "EUR", "BE": "EUR", "PT": "EUR",
    "AT": "EUR", "FI": "EUR", "GR": "EUR", "SG": "SGD", "HK": "HKD", "JP": "JPY", "ZA": "ZAR",
    "AE": "AED", "CH": "CHF", "SE": "SEK", "NO": "NOK", "DK": "DKK", "PL": "PLN", "BR": "BRL",
    "MX": "MXN", "NG": "NGN", "KE": "KES", "PK": "PKR", "PH": "PHP", "MY": "MYR",
}


def lookup(city):
    """Returns {name, label, latitude, longitude, timezone, currency} or None."""
    try:
        results = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1}, timeout=15,
        ).json().get("results") or []
    except Exception:
        return None
    if not results:
        return None
    place = results[0]
    return {
        "name": place["name"],
        "label": ", ".join(x for x in (place["name"], place.get("admin1"), place.get("country")) if x),
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "timezone": place.get("timezone"),
        "currency": CURRENCIES.get((place.get("country_code") or "").upper()),
    }
