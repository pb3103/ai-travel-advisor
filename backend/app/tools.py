"""Live-data tools the advisor agent can call. Plain, deterministic functions — no LLM
judgment here (aside from web_search's own implementation, which just forwards a query to
a hosted search tool and returns its result; it doesn't decide anything on its own).

APIs used, verified directly against their live docs/endpoints before wiring in:
- Frankfurter (https://frankfurter.dev) for exchange rates — free, no API key, ECB data.
- Open-Meteo (https://open-meteo.com) for geocoding + weather — free, no API key.
- OpenRouter's hosted `openrouter:web_search` tool for everything else that needs
  current, real-world facts (visas, advisories, local info) — reuses the same
  OpenRouter key already configured, no separate search API key needed.
"""

import httpx

from .config import settings
from .llm import complete_with_tools

_HTTP_TIMEOUT = 10.0

# WMO weather codes (table 4677), as used by Open-Meteo's `weather_code` field.
WEATHER_CODES = {
    0: "Sunny",
    1: "Mainly sunny",
    2: "Partly cloudy",
    3: "Cloudy",
    45: "Foggy",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Light freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light showers",
    81: "Showers",
    82: "Heavy showers",
    85: "Light snow showers",
    86: "Snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with light hail",
    99: "Thunderstorm with heavy hail",
}


def get_exchange_rate(base: str, quote: str) -> dict:
    """Latest mid-market exchange rate between two currencies."""
    try:
        response = httpx.get(
            f"https://api.frankfurter.dev/v2/rate/{base.strip().lower()}/{quote.strip().lower()}",
            timeout=_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        return {"error": f"Could not fetch the exchange rate: {exc}"}


def get_weather(location: str, date: str | None = None) -> dict:
    """Weather for a place — current conditions (default), or the forecast for a specific
    date up to ~16 days out, so the advisor can reason about a specific day of a trip
    (e.g. 'tomorrow') rather than only ever right now."""
    try:
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1, "language": "en", "format": "json"},
            timeout=_HTTP_TIMEOUT,
        )
        geo.raise_for_status()
        results = geo.json().get("results")
        if not results:
            return {"error": f"Could not find a location matching '{location}'."}
        place = results[0]
        location_label = f"{place['name']}, {place.get('country', '')}".strip(", ")

        forecast = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_sum,precipitation_probability_max"
                ),
                "timezone": "auto",
                "forecast_days": 16,
            },
            timeout=_HTTP_TIMEOUT,
        )
        forecast.raise_for_status()
        data = forecast.json()

        if not date:
            current = data["current"]
            return {
                "location": location_label,
                "local_time": current["time"],
                "temperature_c": current["temperature_2m"],
                "condition": WEATHER_CODES.get(current["weather_code"], "Unknown"),
                "humidity_percent": current["relative_humidity_2m"],
                "precipitation_mm": current["precipitation"],
                "wind_speed_kmh": current["wind_speed_10m"],
            }

        daily = data["daily"]
        if date not in daily["time"]:
            return {
                "error": (
                    f"No forecast available for {date} in {location_label} — forecasts "
                    f"only cover today through {daily['time'][-1]}."
                )
            }
        index = daily["time"].index(date)
        return {
            "location": location_label,
            "date": date,
            "condition": WEATHER_CODES.get(daily["weather_code"][index], "Unknown"),
            "temperature_max_c": daily["temperature_2m_max"][index],
            "temperature_min_c": daily["temperature_2m_min"][index],
            "precipitation_mm": daily["precipitation_sum"][index],
            "precipitation_chance_percent": daily["precipitation_probability_max"][index],
        }
    except httpx.HTTPError as exc:
        return {"error": f"Could not fetch the weather: {exc}"}


def web_search(query: str) -> dict:
    """Search the live web for current travel info (visas, advisories, local requirements)."""
    try:
        response = complete_with_tools(
            model=settings.advisor_model,
            messages=[{"role": "user", "content": query}],
            tools=[{"type": "openrouter:web_search", "parameters": {"max_results": 3}}],
        )
        message = response.choices[0].message
        sources = [
            {"title": annotation.url_citation.title, "url": annotation.url_citation.url}
            for annotation in (message.annotations or [])
            if annotation.type == "url_citation"
        ]
        return {"answer": message.content, "sources": sources}
    except Exception as exc:
        return {"error": f"Web search failed: {exc}"}


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rate",
            "description": "Get the current, live mid-market exchange rate between two currencies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "base": {
                        "type": "string",
                        "description": "Three-letter ISO currency code to convert from, e.g. USD",
                    },
                    "quote": {
                        "type": "string",
                        "description": "Three-letter ISO currency code to convert to, e.g. EUR",
                    },
                },
                "required": ["base", "quote"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "Get the weather for a city or place — current conditions (omit date), or "
                "the forecast for a specific date up to about 16 days out (pass date). Use "
                "the forecast when reasoning about a specific day of a trip, e.g. checking "
                "whether a planned activity suits the weather, not just for right-now questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City or place name, e.g. 'Tokyo' or 'Paris, France'",
                    },
                    "date": {
                        "type": "string",
                        "description": "Optional ISO date (YYYY-MM-DD) to get a forecast for, instead of current conditions",
                    },
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the live web for current travel information that changes over time or "
                "you don't reliably know, such as visa/entry requirements, travel advisories, "
                "local events, or other up-to-date facts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The question to search for"},
                },
                "required": ["query"],
            },
        },
    },
]

TOOL_HANDLERS = {
    "get_exchange_rate": get_exchange_rate,
    "get_weather": get_weather,
    "web_search": web_search,
}
