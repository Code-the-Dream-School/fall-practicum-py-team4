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


@dataclass(frozen=True)
class Coordinates:
    lat: float
    lon: float
    retrieved_at: datetime
    from_cache: bool = False


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


def geocode_city(
    raw_dir: Path, city: str, country_code: str, state: str | None = None,
    *, force_refresh: bool = False, use_cache: bool = True, cache=None,
) -> Coordinates:
    """raw_dir is accepted for compatibility; cache storage is PostgreSQL."""
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
    query_parts.append(country_code)
    params = {"q": ",".join(query_parts), "limit": 5}
    key = hashlib.sha256(json.dumps(
        [1, "/geo/1.0/direct", params, state_name], sort_keys=True,
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
    if cached is None:
        payload = get_json("/geo/1.0/direct", params)
        _validate(payload)
        fetched = utc_now()
        if store:
            store.put(key, payload, fetched, ttl if payload else empty_ttl)
    else:
        payload, fetched = cached
    matches = [item for item in payload
               if item["country"].upper() == country_code
               and (not state_name or str(item.get("state", "")).casefold() == state_name.casefold())]
    unique = {(item["lat"], item["lon"]): item for item in matches}
    if not unique:
        raise OpenWeatherError("No matching city; check city, country and state")
    if len(unique) != 1:
        raise OpenWeatherError("Ambiguous city; provide a more specific city or state")
    item = next(iter(unique.values()))
    return Coordinates(float(item["lat"]), float(item["lon"]), fetched, cached is not None)
