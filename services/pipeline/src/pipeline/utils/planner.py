from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

class AirPollutionPlanner:
  """
  Execution planner for the Prefect Orchestrated Air Pollution Pipeline. 

  The AirPollutionPlanner inspects Supabase data layers to detect and batch 
  missing or incomplete daily air pollution records.

  Automatically maps raw city name strings to their corresponding primary keys (`city_id`)
  in the `gold_cities` table, If the city doesnt exists on the gold table, the planner
  passes the name of the city, sets city_id to None and fills the 60 days of missing dates,
  ready for backfilling mode.

  Queries hourly timestamp data (`date_time`) using progressive chunking to safely bypass
  supabase row limits (1000), flagging any calendar date with fewer than 24 records as incomplete
  or missing.
  
  Automatically shifts sorting behavior based on backlog size, prioritizing oldest-first (backfill)
  for large data gaps (more than 15 days, defined by 'chunk size') and most recent-first
  (incremental mode) when nearing real-time (less than 15 days).

  returns a dict containing: {city_name, city_id, list[missing_dates]
  """

  def __init__(
      self, 
      cities: list[str] = None,  
      window_days: int = 60,  # Number of past days to inspect for missing data
      chunk_size: int = 15,  # Define chunk size, has to be safe for Supabase limits (< 41 days or 1000 rows)
      supabase_client=None
  ):
    if not cities:
      raise ValueError(
          "A list of cities must be provided for the pipeline execution."
      )
    # Normalize casing, strip spacing, and remove duplicates safely
    normalized_raw = [city.strip().lower() for city in cities]
    self.cities = list(dict.fromkeys(normalized_raw))
    self.window_days = window_days
    self.chunk_size = chunk_size
    self._supabase = supabase_client

  @property
  def supabase(self) -> Client:
    """Lazy initialization of the Supabase client."""
    if self._supabase is None:
      supabase_url = os.getenv("SUPABASE_URL")
      supabase_key = os.getenv("SUPABASE_KEY")
      if not supabase_url or not supabase_key:
        raise ValueError(
            "Missing SUPABASE_URL or SUPABASE_KEY in environment variables."
        )
      self._supabase = create_client(supabase_url, supabase_key)
    return self._supabase

  def get_city_id(self, city_name: str) -> int | None:
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
        return response.data[0].get("id")
    except Exception:
      pass
    return None

  def _get_expected_dates(self) -> list[str]:
    """Generates the full list of expected dates for the window up to yesterday."""
    today = datetime.now(timezone.utc).date()
    start_window = today - timedelta(days=self.window_days)
    end_window = today - timedelta(days=1)  # Yesterday

    expected_dates = set()
    current_dt = start_window
    while current_dt <= end_window:
      expected_dates.add(current_dt.strftime("%Y-%m-%d"))
      current_dt += timedelta(days=1)

    return sorted(list(expected_dates))

  def get_missing_dates_for_city_id(self, city_id: int) -> list[str]:
    """Inspects the gold hourly layer using progressive 30-day chunks 
    to safely bypass Supabase row limits for large historical windows.
    """

    today = datetime.now(timezone.utc).date()
    start_window = today - timedelta(days=self.window_days)
    end_window = today - timedelta(days=1)  # Yesterday

    date_counts = {}
    
    current_chunk_start = start_window

    try:
      while current_chunk_start <= end_window:
        current_chunk_end = min(current_chunk_start + timedelta(days=self.chunk_size - 1), end_window)
        
        # Query just this specific chunk
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
    except Exception:
      completed_dates = set()

    expected_dates = set(self._get_expected_dates())

    return sorted(list(expected_dates - completed_dates))

  def create_execution_plan(self, max_dates_per_city: int = None) -> list[dict]:
    """Returns an execution plan listing every city, its corresponding id and
    a chunk of specific dates it needs to fetch (enabling progressive loading).
    
    :param max_dates_per_city: Limits the number of missing dates processed 
    per city in this run (e.g., 7 days at a time).
    """
    plan = []
    for city_name in self.cities:
      city_id = self.get_city_id(city_name)

      if city_id is None:
        # If city is not found in gold_cities, treat the entire window as missing
        missing_dates = self._get_expected_dates()
      else:
        missing_dates = self.get_missing_dates_for_city_id(city_id)

      if missing_dates:
        if len(missing_dates) > self.chunk_size:
          pass
        else:
          missing_dates = sorted(missing_dates, reverse=True)

        # Apply batch limit AFTER sorting so slicing grabs the correct end of the spectrum
        if max_dates_per_city and len(missing_dates) > max_dates_per_city:
          # Take only the first N dates for this batch
          missing_dates = missing_dates[:max_dates_per_city]
        
        plan.append({
            "city_name": city_name,
            "city_id": city_id,
            "missing_dates": missing_dates
        })
        
    return plan