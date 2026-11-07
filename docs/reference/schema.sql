--
-- PostgreSQL database dump
--

\restrict 1KGuKSYI1QK2ONedzQVtIrczngBO5HPC3vfZs6AckuOmV6NoTWhfF9eMDgNNMfT

-- Dumped from database version 17.11
-- Dumped by pg_dump version 17.11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: aqi_to_sentiment(integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.aqi_to_sentiment(aqi integer) RETURNS text
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN CASE aqi
        WHEN 1 THEN 'Good'
        WHEN 2 THEN 'Fair'
        WHEN 3 THEN 'Moderate'
        WHEN 4 THEN 'Poor'
        WHEN 5 THEN 'Very Poor'
        ELSE NULL
    END;
END;
$$;


--
-- Name: update_pm25_running_average(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_pm25_running_average() RETURNS void
    LANGUAGE sql
    AS $$
    WITH rolling AS (
        SELECT
            id,
            AVG(pm2_5) OVER (
                PARTITION BY city
                ORDER BY date_time
                RANGE BETWEEN INTERVAL '10 days' PRECEDING
                AND CURRENT ROW
            ) AS avg_pm25
        FROM public.gold_air_data
    )
    UPDATE public.gold_air_data AS g
    SET running_average = r.avg_pm25
    FROM rolling AS r
    WHERE g.id = r.id
      AND g.running_average IS DISTINCT FROM r.avg_pm25;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: gold_air_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.gold_air_data (
    id bigint NOT NULL,
    co double precision,
    pm2_5 double precision,
    no2 double precision,
    retrieve_date date,
    aqi integer,
    sentiment_label text,
    city_id bigint,
    date_time timestamp with time zone,
    aqi_rolling_7d double precision,
    pm2_5_rolling_7d double precision
);


--
-- Name: gold_cities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.gold_cities (
    id bigint NOT NULL,
    city text,
    state text,
    lat double precision,
    lon double precision,
    population bigint,
    elevation double precision,
    country text
);


--
-- Name: gold_cities_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.gold_cities_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: gold_cities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.gold_cities_id_seq OWNED BY public.gold_cities.id;


--
-- Name: gold_table_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.gold_table_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: gold_table_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.gold_table_id_seq OWNED BY public.gold_air_data.id;


--
-- Name: pipeline_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pipeline_runs (
    id bigint NOT NULL,
    status text NOT NULL,
    records_added integer DEFAULT 0,
    runs_time double precision,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: pipeline_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pipeline_runs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pipeline_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pipeline_runs_id_seq OWNED BY public.pipeline_runs.id;


--
-- Name: raw_air_pollution; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.raw_air_pollution (
    id bigint NOT NULL,
    payload jsonb,
    city text,
    extracted_at date DEFAULT now(),
    target_date date
);


--
-- Name: raw_cities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.raw_cities (
    id bigint NOT NULL,
    city text,
    payload jsonb,
    extracted_at date DEFAULT now()
);


--
-- Name: raw_cities_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.raw_cities_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: raw_cities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.raw_cities_id_seq OWNED BY public.raw_cities.id;


--
-- Name: raw_table_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.raw_table_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: raw_table_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.raw_table_id_seq OWNED BY public.raw_air_pollution.id;


--
-- Name: gold_air_data id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gold_air_data ALTER COLUMN id SET DEFAULT nextval('public.gold_table_id_seq'::regclass);


--
-- Name: gold_cities id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gold_cities ALTER COLUMN id SET DEFAULT nextval('public.gold_cities_id_seq'::regclass);


--
-- Name: pipeline_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_runs ALTER COLUMN id SET DEFAULT nextval('public.pipeline_runs_id_seq'::regclass);


--
-- Name: raw_air_pollution id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.raw_air_pollution ALTER COLUMN id SET DEFAULT nextval('public.raw_table_id_seq'::regclass);


--
-- Name: raw_cities id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.raw_cities ALTER COLUMN id SET DEFAULT nextval('public.raw_cities_id_seq'::regclass);


--
-- Name: gold_cities gold_cities_city_name_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gold_cities
    ADD CONSTRAINT gold_cities_city_name_unique UNIQUE (city);


--
-- Name: gold_cities gold_cities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gold_cities
    ADD CONSTRAINT gold_cities_pkey PRIMARY KEY (id);


--
-- Name: gold_air_data gold_table_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gold_air_data
    ADD CONSTRAINT gold_table_pkey PRIMARY KEY (id);


--
-- Name: pipeline_runs pipeline_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_runs
    ADD CONSTRAINT pipeline_runs_pkey PRIMARY KEY (id);


--
-- Name: raw_cities raw_cities_city_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.raw_cities
    ADD CONSTRAINT raw_cities_city_unique UNIQUE (city);


--
-- Name: raw_cities raw_cities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.raw_cities
    ADD CONSTRAINT raw_cities_pkey PRIMARY KEY (id);


--
-- Name: raw_air_pollution raw_table_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.raw_air_pollution
    ADD CONSTRAINT raw_table_pkey PRIMARY KEY (id);


--
-- Name: gold_air_data gold_air_data_city_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gold_air_data
    ADD CONSTRAINT gold_air_data_city_id_fkey FOREIGN KEY (city_id) REFERENCES public.gold_cities(id);


--
-- PostgreSQL database dump complete
--

\unrestrict 1KGuKSYI1QK2ONedzQVtIrczngBO5HPC3vfZs6AckuOmV6NoTWhfF9eMDgNNMfT

