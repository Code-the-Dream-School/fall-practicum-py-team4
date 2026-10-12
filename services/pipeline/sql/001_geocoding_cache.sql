-- Apply once to the PostgreSQL database identified by DATABASE_URL.
CREATE TABLE IF NOT EXISTS public.openweather_geocoding_cache (
    cache_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'array'),
    fetched_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL CHECK (expires_at >= fetched_at)
);

CREATE INDEX IF NOT EXISTS openweather_geocoding_cache_expiry_idx
    ON public.openweather_geocoding_cache (expires_at);
