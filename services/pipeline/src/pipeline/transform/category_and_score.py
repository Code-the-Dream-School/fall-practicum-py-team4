"""T4AIR-20: AQI category and PM2.5 score. Plain values in and out, no database."""

import math
from collections.abc import Mapping
from typing import Any

# WHO 2021 24-hour PM2.5 guideline, in µg/m³. Used as a fixed comparison point.
PM25_REFERENCE_UG_M3 = 15.0

AQI_CATEGORIES = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very Poor"}


def _finite_number(value: Any, field: str) -> float:
    # Reject bools and strings instead of silently coercing them.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    try:
        number = float(value)
    except OverflowError:
        raise ValueError(f"{field} must be a finite number") from None
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    return number


def aqi_to_category(aqi: int | float) -> str:
    """OpenWeather AQI 1-5 -> Good / Fair / Moderate / Poor / Very Poor.

    Integral floats such as 2.0 are accepted; fractions are never rounded.
    """
    number = _finite_number(aqi, "aqi")
    if not number.is_integer() or number not in AQI_CATEGORIES:
        raise ValueError("aqi must be an integer from 1 through 5")
    return AQI_CATEGORIES[int(number)]


def pm25_to_score(pm2_5: int | float) -> float:
    """PM2.5 as a percentage of the WHO reference: pm2_5 / 15 * 100.

    100 means equal to the reference; values above 100 are not capped.
    """
    concentration = _finite_number(pm2_5, "pm2_5")
    if concentration < 0:
        raise ValueError("pm2_5 must be nonnegative")
    score = concentration * (100.0 / PM25_REFERENCE_UG_M3)
    if not math.isfinite(score):
        raise ValueError("pm2_5 is too large to produce a finite score")
    return score


def reading_to_score(reading: Mapping[str, Any]) -> float:
    """Score a raw or gold reading that has components.pm2_5."""
    if not isinstance(reading, Mapping):
        raise ValueError("reading must be a mapping")
    components = reading.get("components")
    if not isinstance(components, Mapping):
        raise ValueError("reading.components must be a mapping")
    if "pm2_5" not in components:
        raise ValueError("reading.components.pm2_5 is required")
    return pm25_to_score(components["pm2_5"])


def reading_aqi(reading: Mapping[str, Any]) -> Any:
    """Gold readings carry `aqi`; raw OpenWeather rows carry `main.aqi`."""
    if "aqi" in reading:
        return reading["aqi"]
    main = reading.get("main")
    return main.get("aqi") if isinstance(main, Mapping) else None


def add_category_and_score(readings: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return copies of the readings with aqi_category and risk_score set.

    Existing derived values are recalculated, so calling this twice is safe.
    A bad reading raises ValueError naming its index; nothing becomes zero.
    """
    if not isinstance(readings, list):
        raise ValueError("readings must be a list")
    result = []
    for index, reading in enumerate(readings):
        if not isinstance(reading, Mapping):
            raise ValueError(f"readings[{index}] must be a mapping")
        try:
            category = aqi_to_category(reading_aqi(reading))
            score = reading_to_score(reading)
        except ValueError as error:
            raise ValueError(f"readings[{index}]: {error}") from error
        result.append({**reading, "aqi_category": category, "risk_score": score})
    return result
