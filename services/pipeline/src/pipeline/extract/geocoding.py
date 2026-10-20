"""Resolve one city for the team's existing orchestration call."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .lookup_cache import PostgresLookupCache
from .openweather_http import (
    InputError, OpenWeatherError, coordinate, env_seconds,
    get_json, location_input, utc_now,
)

_US_STATES = dict(item.split(":") for item in (
    "AL:Alabama|AK:Alaska|AZ:Arizona|AR:Arkansas|CA:California|CO:Colorado|"
    "CT:Connecticut|DE:Delaware|DC:District of Columbia|FL:Florida|GA:Georgia|"
    "HI:Hawaii|ID:Idaho|IL:Illinois|IN:Indiana|IA:Iowa|KS:Kansas|KY:Kentucky|"
    "LA:Louisiana|ME:Maine|MD:Maryland|MA:Massachusetts|MI:Michigan|MN:Minnesota|"
    "MS:Mississippi|MO:Missouri|MT:Montana|NE:Nebraska|NV:Nevada|NH:New Hampshire|"
    "NJ:New Jersey|NM:New Mexico|NY:New York|NC:North Carolina|ND:North Dakota|"
    "OH:Ohio|OK:Oklahoma|OR:Oregon|PA:Pennsylvania|RI:Rhode Island|"
    "SC:South Carolina|SD:South Dakota|TN:Tennessee|TX:Texas|UT:Utah|VT:Vermont|"
    "VA:Virginia|WA:Washington|WV:West Virginia|WI:Wisconsin|WY:Wyoming|"
    "PR:Puerto Rico|VI:United States Virgin Islands|GU:Guam|AS:American Samoa|"
    "MP:Northern Mariana Islands"
).split("|"))


DIRECT_PATH = "/geo/1.0/direct"
ZIP_PATH = "/geo/1.0/zip"


@dataclass(frozen=True)
class Coordinates:
    lat: float
    lon: float
    retrieved_at: datetime
    from_cache: bool = False
    # Kept so gold can add state if the team keeps a U.S.-only scope.
    country: str | None = None
    state: str | None = None


def _validate(payload):
    if not isinstance(payload, list):
        raise OpenWeatherError("Expected a geocoding result list")
    for item in payload:
        if (not isinstance(item, dict) or not isinstance(item.get("name"), str)
                or not isinstance(item.get("country"), str)):
            raise OpenWeatherError("Malformed geocoding result")
        try:
            coordinate(item.get("lat"), "lat", -90, 90)
            coordinate(item.get("lon"), "lon", -180, 180)
        except InputError:
            raise OpenWeatherError("Malformed geocoding coordinates") from None


def _lookup(path, params, key_extra, *, force_refresh, use_cache, cache):
    """Cached geocoding GET; returns (candidate list, fetched_at, from_cache)."""
    key = hashlib.sha256(json.dumps(
        [1, path, params, key_extra], sort_keys=True,
    ).encode()).hexdigest()
    ttl = env_seconds("OPENWEATHER_LOOKUP_TTL_SECONDS", 2592000, allow_zero=True)
    empty_ttl = env_seconds("OPENWEATHER_EMPTY_LOOKUP_TTL_SECONDS", 3600, allow_zero=True)
    store = (cache if cache is not None else PostgresLookupCache()) if use_cache else None
    cached = store.get(key, utc_now(), ttl, empty_ttl) if store and not force_refresh else None
    if cached is not None:
        try:
            _validate(cached[0])
        except OpenWeatherError:
            cached = None
    if cached is not None:
        return cached[0], cached[1], True
    payload = get_json(path, params)
    if path == ZIP_PATH:
        # The zip endpoint returns one object; the cache table stores lists.
        payload = [payload] if isinstance(payload, dict) and payload else []
    _validate(payload)
    fetched = utc_now()
    if store:
        store.put(key, payload, fetched, ttl if payload else empty_ttl)
    return payload, fetched, False


def _coordinates(item, fetched, from_cache):
    return Coordinates(
        float(item["lat"]), float(item["lon"]), fetched, from_cache,
        country=item["country"].upper(), state=item.get("state") or None,
    )


def geocode_city(
    raw_dir: Path | None, city: str, country_code: str | None, state: str | None = None,
    *, force_refresh: bool = False, use_cache: bool = True, cache=None,
) -> Coordinates:
    """raw_dir is accepted for compatibility; cache storage is PostgreSQL.

    With a country code, more than one distinct match is an error. Without one
    (data_contracts input is a bare city name) the provider's top result is used.
    """
    city, country_code, state = location_input(city, country_code, state)
    state_name = state
    query_parts = [city]
    if state and country_code == "US":
        code = next((code for code, name in _US_STATES.items()
                     if state.upper() == code or state.casefold() == name.casefold()), None)
        if code is None:
            raise InputError("Use a recognized US state name or postal code")
        state_name = _US_STATES[code]
        query_parts.append(code)
    if country_code:
        query_parts.append(country_code)
    params = {"q": ",".join(query_parts), "limit": 5}
    payload, fetched, from_cache = _lookup(
        DIRECT_PATH, params, state_name,
        force_refresh=force_refresh, use_cache=use_cache, cache=cache,
    )
    matches = [item for item in payload
               if (not country_code or item["country"].upper() == country_code)
               and (not state_name or str(item.get("state", "")).casefold() == state_name.casefold())]
    unique = {(item["lat"], item["lon"]): item for item in matches}
    if not unique:
        raise OpenWeatherError("No matching city; check city, country and state")
    if country_code and len(unique) != 1:
        raise OpenWeatherError("Ambiguous city; provide a more specific city or state")
    return _coordinates(next(iter(unique.values())), fetched, from_cache)


def geocode_zip(
    zip_code: str, country_code: str = "US",
    *, force_refresh: bool = False, use_cache: bool = True, cache=None,
) -> Coordinates:
    """Resolve a postal code (data_contracts `cities` accepts zipcodes)."""
    if not isinstance(zip_code, str) or not zip_code.strip() or "," in zip_code:
        raise InputError("Provide a postal code without commas")
    _, country_code, _ = location_input("zip", country_code)
    params = {"zip": f"{zip_code.strip()},{country_code}"}
    payload, fetched, from_cache = _lookup(
        ZIP_PATH, params, None, force_refresh=force_refresh, use_cache=use_cache, cache=cache,
    )
    if not payload:
        raise OpenWeatherError("No matching postal code")
    return _coordinates(payload[0], fetched, from_cache)
