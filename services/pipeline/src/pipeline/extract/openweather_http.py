"""Shared request boundary. Never log authenticated URLs or response errors."""

import json
import math
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

BASE_URL = "https://api.openweathermap.org"
MAX_BODY_BYTES = 10 * 1024 * 1024


class InputError(ValueError):
    pass


class ConfigurationError(ValueError):
    pass


class OpenWeatherError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def env_seconds(name, default, *, allow_zero=False):
    try:
        value = float(os.getenv(name, str(default)))
        if not math.isfinite(value) or value < 0 or value > 31_536_000:
            raise ValueError
        if value == 0 and not allow_zero:
            raise ValueError
        return value
    except ValueError:
        raise ConfigurationError(f"Invalid setting: {name}") from None


def coordinate(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{name} must be a finite number")
    try:
        value = float(value)
    except OverflowError:
        raise InputError(f"Invalid {name}") from None
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise InputError(f"Invalid {name}")
    return value


def location_input(city, country_code, state=None):
    if not isinstance(city, str) or not city.strip() or "," in city:
        raise InputError("Provide a city name without comma-separated fields")
    if (not isinstance(country_code, str) or len(country_code.strip()) != 2
            or not country_code.strip().isascii()
            or not country_code.strip().isalpha()):
        raise InputError("country_code must contain two letters")
    if state is not None and (not isinstance(state, str) or "," in state):
        raise InputError("state must be a name or code")
    city = " ".join(city.split())
    state = " ".join(state.split()) if state else None
    return city, country_code.strip().upper(), state or None


def _retry_delay(value, attempt):
    delay = 0.5 * (2 ** attempt)
    if value:
        try:
            requested = float(value)
        except (TypeError, ValueError):
            try:
                requested = parsedate_to_datetime(value).timestamp() - time.time()
            except (TypeError, ValueError, OverflowError):
                requested = 0
        if math.isfinite(requested):
            delay = max(delay, requested)
    return delay


def _invalid_constant(value):
    raise ValueError("Invalid JSON constant")


def get_json(path: str, params: dict):
    """GET with three attempts, bounded waits, TLS and no redirects."""
    if path not in ("/geo/1.0/direct", "/data/2.5/air_pollution/history"):
        raise InputError("Unsupported OpenWeather endpoint")
    key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if not key:
        raise ConfigurationError("Set OPENWEATHER_API_KEY")
    timeout = env_seconds("OPENWEATHER_TIMEOUT_SECONDS", 15)
    for attempt in range(3):
        try:
            with requests.get(
                BASE_URL + path,
                params={**params, "appid": key},
                timeout=(5, timeout),
                allow_redirects=False,
                stream=True,
            ) as response:
                status = response.status_code
                if status in (429, 500, 502, 503, 504):
                    delay = _retry_delay(response.headers.get("Retry-After"), attempt)
                    if attempt == 2 or delay > 30:
                        raise OpenWeatherError(f"OpenWeather HTTP {status}; retry later")
                elif not 200 <= status < 300:
                    raise OpenWeatherError(f"OpenWeather HTTP {status}")
                else:
                    body = bytearray()
                    for chunk in response.iter_content(65536):
                        body.extend(chunk)
                        if len(body) > MAX_BODY_BYTES:
                            raise OpenWeatherError("OpenWeather response exceeds 10 MiB")
                    try:
                        return json.loads(body, parse_constant=_invalid_constant)
                    except (ValueError, UnicodeError):
                        raise OpenWeatherError("OpenWeather returned invalid JSON") from None
        except requests.RequestException:
            if attempt == 2:
                raise OpenWeatherError("OpenWeather connection failed after three attempts") from None
            delay = 0.5 * (2 ** attempt)
        time.sleep(delay)
