from datetime import datetime, timedelta, timezone
import os
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logger = logging.getLogger(__name__)

class AirPollutionPlanner:
  """
  Execution planner for the Prefect Orchestrated Air Pollution Pipeline. 

  Supports two execution modes:
  - backfill: inspects and processes a specified historical window (window_days).
  - incremental: inspects and processes only what is new since the last successful
    flow run recorded in the pipeline_runs table.

  The AirPollutionPlanner inspects Supabase data layers to detect and batch 
  missing or incomplete daily air pollution records.

  Maps city name to the corresponding primary key (`city_id`) in the `gold_cities` table,
  queries hourly timestamp data (`date_time`) using progressive chunking to safely bypass
  supabase row limits (1000), flagging any calendar date with fewer than 24 records as incomplete
  or missing.

  returns a dict containing: {city_name, city_id, list[missing_dates]}
  """

  def __init__(
      self, 
      cities: list[str] = None, 
      mode: str = 'incremental', 
      window_days: int = 60,  # Number of past days to inspect for missing data
      chunk_size: int = 15,  # Define chunk size, has to be safe for Supabase limits (< 41 days or 1000 rows)
      supabase_client=None
  ):
    if not cities or not any(c.strip() for c in cities if isinstance(c, str)):
      raise ValueError(
          "A list of cities must be provided for the pipeline execution."
      )
    # Normalize casing, strip spacing, and remove duplicates safely
    normalized_raw = [city.strip().lower() for city in cities if isinstance(city, str) and city.strip()]
    self.cities = list(dict.fromkeys(normalized_raw))
    self.mode = mode.lower().strip()
    self.window_days = window_days
    self.chunk_size = chunk_size
    self._supabase = supabase_client

    if self.mode not in ["backfill", "incremental"]:
      raise ValueError("Pipeline mode must be either 'backfill' or 'incremental'.")
    if self.window_days < 1:
      raise ValueError("window_days must be at least 1.")
    if not (1 <= self.chunk_size <= 40):
      raise ValueError("chunk_size must be between 1 and 40 days to stay under Supabase's 1000-row limit.")

    logger.info(f"Initialized AirPollutionPlanner for cities: {self.cities} | Mode: {self.mode.upper()}")

  @property
  def supabase(self) -> Client:
    """Lazy initialization of the Supabase client."""
    if self._supabase is None:
      supabase_url = os.getenv("SUPABASE_URL")
      supabase_key = os.getenv("SUPABASE_KEY")
      if not supabase_url or not supabase_key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in environment variables.")
      self._supabase = create_client(supabase_url, supabase_key)
    return self._supabase


  def get_city_id(self, city_name: str) -> int | str | None:
    """Looks up the corresponding city_id from the gold_cities table."""
    normalized_city = city_name.strip().lower()
    try:
      response = (
          self.supabase.table("gold_cities")
          .select("id")
          .eq("city", normalized_city)
          .limit(1)
          .execute()
      )
      if response.data:
        city_id = response.data[0].get("id")
        logger.debug(f"Found city_id {city_id} for city '{normalized_city}'")
        return city_id
    except Exception as e:
      logger.warning(f"Could not fetch city_id for '{normalized_city}': {e}")
      return None

    logger.info(f"City '{normalized_city}' not found in gold_cities.")
    return None


  def get_last_successful_run_time(self) -> datetime | None:
    """Queries the pipeline_runs table for the most recent successful 
    flow execution timestamp, ensuring incremental mode advances correctly.
    """
    try:
      response = (
          self.supabase.table("pipeline_runs")
          .select("created_at")
          .eq("process", "City Air Tracker ETL")  # Flow process name
          .eq("status", "SUCCESS")
          .order("created_at", desc=True)
          .limit(1)
          .execute()
      )
      if response.data:
        dt_str = response.data[0].get("created_at")
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception as e:
      logger.warning(f"Warning: Could not fetch last run time from pipeline_runs: {e}.")
    return None


  def _get_expected_dates(self) -> list[str]:
    """Generates the full list of expected dates for the window up to yesterday."""
    today = datetime.now(timezone.utc).date()
    end_window = today - timedelta(days=1)  # Yesterday

    if self.mode == "incremental":
      last_run = self.get_last_successful_run_time()
      if last_run:
        start_window = last_run.date()
        logger.info(f"Incremental mode: using last successful run date ({start_window}) as start window.")
      else:
        # Fallback to yesterday if no data exists
        start_window = today - timedelta(days=1)
        logger.warning(f"Incremental mode: No prior run record found. Falling back to yesterday ({start_window}).")
    else:
      start_window = today - timedelta(days=self.window_days)
      logger.info(f"Backfill mode: using full historical window of {self.window_days} days (from {start_window}).")

    expected_dates = []
    current_dt = start_window
    while current_dt <= end_window:
      expected_dates.append(current_dt.strftime("%Y-%m-%d"))
      current_dt += timedelta(days=1)

    return expected_dates


  def get_missing_dates_for_city_id(self, city_id: int | str, expected_dates: list[str]) -> list[str]:
    """Inspects the gold hourly layer using progressive chunks to safely
    bypass Supabase row limits for large historical windows.
    """
      
    if not expected_dates:
      return []

    start_window = datetime.strptime(expected_dates[0], "%Y-%m-%d").date()
    end_window = datetime.strptime(expected_dates[-1], "%Y-%m-%d").date()

    date_counts = {}
    current_chunk_start = start_window

    try:
      while current_chunk_start <= end_window:
        current_chunk_end = min(current_chunk_start + timedelta(days=self.chunk_size - 1), end_window)
        
        response = (
            self.supabase.table("gold_air_data")
            .select("date_time")
            .eq("city_id", city_id)
            .gte("date_time", f"{current_chunk_start.strftime('%Y-%m-%d')}T00:00:00")
            .lte("date_time", f"{current_chunk_end.strftime('%Y-%m-%d')}T23:59:59")
            .execute()
        )
        
        for row in response.data:
          dt_val = row["date_time"]
          # Extract just the 'YYYY-MM-DD' part from the timestamp string
          date_str = str(dt_val)[:10]
          date_counts[date_str] = date_counts.get(date_str, 0) + 1
          
        # Move to the next chunk
        current_chunk_start = current_chunk_end + timedelta(days=1)

      # A date is complete if it has all 24 hourly records
      completed_dates = {d for d, count in date_counts.items() if count >= 24}
    except Exception as e:
      logger.error(f"Error querying gold_air_data for city_id {city_id}: {e}")
      # Retain any dates already verified before the chunk error
      completed_dates = {d for d, count in date_counts.items() if count >= 24}

    expected_dates = set(expected_dates)
    return sorted(list(expected_dates - completed_dates))


  def create_execution_plan(self, max_dates_per_city: int = None) -> list[dict]:
    """Returns an execution plan listing every city, its corresponding id and
    a chronological chunk of specific dates it needs to fetch (oldest-first),
    ensuring accurate sequential 7-day rolling average calculations.
    
    :param max_dates_per_city: Limits the number of missing dates processed 
    per city in this run (e.g., 7 days at a time).
    """

    logger.info("Generating execution plan...")

    # Pre-compute standard expected dates once per run to avoid N+1 pipeline_runs queries
    standard_expected_dates = self._get_expected_dates()

    plan = []
    for city_name in self.cities:
      city_id = self.get_city_id(city_name)

      if city_id is None:
        # New city: respects current mode so unit tests pass, or pass force_full_window=True if desired
        missing_dates = list(standard_expected_dates)
      else:
        missing_dates = self.get_missing_dates_for_city_id(city_id, expected_dates=standard_expected_dates)

      if missing_dates:
        # Apply batch limit AFTER sorting so slicing grabs the correct end of the spectrum
        if max_dates_per_city and len(missing_dates) > max_dates_per_city:
          # Take only the first N dates for this batch
          missing_dates = missing_dates[:max_dates_per_city]
        
        plan.append({
            "city_name": city_name,
            "city_id": city_id,
            "missing_dates": missing_dates
        })

        logger.info(f"Planned city '{city_name}': {len(missing_dates)} dates scheduled for ingestion.")
      else:
        logger.info(f"City '{city_name}' is fully up to date. No missing dates found.")

    logger.info(f"Execution plan completed. Total cities requiring work: {len(plan)}")        
    return plan