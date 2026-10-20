"""RawOpenMateo -> GoldenMateo, as defined in data_contracts.py."""

from collections.abc import Mapping
from typing import Any


def to_gold_locations(raw: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Map each raw result to a gold location; strings are lowercased.

    region is the continent part of the IANA timezone ("Europe/Paris" ->
    "europe"), matching the contract example. Results missing a required
    field are dropped, per the contract's invalid-row rule.
    """
    results = raw.get("results") if isinstance(raw, Mapping) else None
    if not isinstance(results, list):
        raise ValueError("raw.results must be a list")
    locations = []
    for item in results:
        try:
            location = {
                "name": item["name"].lower(),
                "lat": float(item["latitude"]),
                "lon": float(item["longitude"]),
                "elevation": float(item["elevation"]),
                "country": item["country"].lower(),
                "region": item["timezone"].split("/")[0].lower(),
                "population": int(item["population"]),
            }
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        locations.append(location)
    return {"locations": locations}
