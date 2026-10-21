"""PostgreSQL cache. Apply the accompanying SQL migration before use."""

import logging
import os
from datetime import timedelta

import psycopg
from psycopg.types.json import Jsonb

LOG = logging.getLogger(__name__)


class PostgresLookupCache:
    def __init__(self, dsn=None):
        self._dsn = dsn if dsn is not None else os.getenv("DATABASE_URL", "")
        self._dsn = self._dsn.replace("postgresql+psycopg://", "postgresql://", 1)
        if not self._dsn:
            LOG.warning("DATABASE_URL is missing; lookup caching is disabled")

    def _connect(self):
        return psycopg.connect(
            self._dsn, connect_timeout=3,
            options="-c statement_timeout=3000",
        )

    def get(self, key, now, ttl, empty_ttl):
        if not self._dsn:
            return None
        try:
            with self._connect() as db:
                row = db.execute(
                    """SELECT payload, fetched_at, expires_at
                       FROM public.openweather_geocoding_cache
                       WHERE cache_key = %s""", (key,),
                ).fetchone()
            if row is None:
                return None
            payload, fetched, expires = row
            if not isinstance(payload, list):
                return None
            lifetime = ttl if payload else empty_ttl
            if not fetched <= now < min(expires, fetched + timedelta(seconds=lifetime)):
                return None
            return payload, fetched
        except (psycopg.Error, OSError, TypeError, ValueError, OverflowError):
            LOG.warning("Lookup cache unavailable; requesting source data")
            return None

    def put(self, key, payload, fetched, ttl):
        if not self._dsn or ttl <= 0:
            return
        try:
            with self._connect() as db:
                db.execute(
                    """INSERT INTO public.openweather_geocoding_cache
                       (cache_key, payload, fetched_at, expires_at)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (cache_key) DO UPDATE SET
                         payload = EXCLUDED.payload,
                         fetched_at = EXCLUDED.fetched_at,
                         expires_at = EXCLUDED.expires_at
                       WHERE openweather_geocoding_cache.fetched_at
                             <= EXCLUDED.fetched_at""",
                    (key, Jsonb(payload), fetched, fetched + timedelta(seconds=ttl)),
                )
                db.execute(
                    "DELETE FROM public.openweather_geocoding_cache WHERE expires_at <= %s",
                    (fetched,),
                )
        except (psycopg.Error, OSError, TypeError, ValueError, OverflowError):
            LOG.warning("Lookup cache write failed; using source data")
