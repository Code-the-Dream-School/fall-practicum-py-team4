from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest
from pipeline.utils.planner import AirPollutionPlanner


@pytest.fixture
def mock_supabase_client():
  """Fixture to create a mock Supabase client."""
  client = MagicMock()
  return client


@pytest.mark.unit
def test_planner_backfill_mode_empty_database(mock_supabase_client):
  """Test backfill mode with city_id lookup: when no records exist, all dates are missing."""
  
  # 1. Mock response for gold_cities lookup: returns a city_id for "bogota"
  mock_city_response = MagicMock()
  mock_city_response.data = [{"id": "city-uuid-bogota-123"}]

  # 2. Mock response for gold_air_pollution_hourly: returns empty data (backfill needed)
  mock_data_response = MagicMock()
  mock_data_response.data = []

  # Configure table routing behavior on the mock client
  def table_side_effect(table_name):
    table_mock = MagicMock()
    if table_name == "gold_cities":
      table_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_city_response
    elif table_name == "gold_air_data":
      table_mock.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = mock_data_response
    elif table_name == "pipeline_runs":
      # Backfill mode doesn't query pipeline_runs, but safe to mock empty
      table_mock.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    return table_mock

  mock_supabase_client.table.side_effect = table_side_effect

  planner = AirPollutionPlanner(cities=["Bogota"], mode='backfill', supabase_client=mock_supabase_client)
  plan = planner.create_execution_plan()

  # Assertions
  assert len(plan) == 1
  assert plan[0]["city_name"] == "bogota"
  assert plan[0]["city_id"] == "city-uuid-bogota-123"
  assert len(plan[0]["missing_dates"]) == 60
  # Verify chronological oldest-first ordering for sequential rolling averages
  assert plan[0]["missing_dates"] == sorted(plan[0]["missing_dates"])


@pytest.mark.unit
def test_planner_incremental_mode_up_to_date(mock_supabase_client):
  """Test incremental mode with city_id: when all dates have >= 24 records, plan is empty."""
  yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
  yesterday_iso = datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc).isoformat()

  mock_city_response = MagicMock()
  mock_city_response.data = [{"id": "city-uuid-london-456"}]

  # Mock last successful run as yesterday at midnight
  mock_run_response = MagicMock()
  mock_run_response.data = [{"created_at": yesterday_iso, "status": "SUCCESS"}]

  # Generate 24 records for every single day in the 60-day window
  mock_data = []
  for hour in range(24):
    mock_data.append({"date_time": f"{yesterday.strftime('%Y-%m-%d')}T{hour:02d}:00:00+00:00"})

  mock_data_response = MagicMock()
  mock_data_response.data = mock_data

  pipeline_runs_table_mock = MagicMock()
  pipeline_runs_table_mock.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_run_response

  def table_side_effect(table_name):
    table_mock = MagicMock()
    if table_name == "gold_cities":
      table_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_city_response
    elif table_name == "pipeline_runs":
      return pipeline_runs_table_mock
    elif table_name == "gold_air_data":
      table_mock.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = mock_data_response
    return table_mock

  mock_supabase_client.table.side_effect = table_side_effect

  planner = AirPollutionPlanner(
      cities=["London"], mode='incremental', supabase_client=mock_supabase_client
  )
  plan = planner.create_execution_plan()

  # Incremental check with complete data results in an empty plan
  assert plan == []
  # Verify the exact Prefect flow name "City Air Tracker ETL" is queried
  pipeline_runs_table_mock.select.return_value.eq.assert_called_once_with("process", "City Air Tracker ETL")


@pytest.mark.unit
def test_incremental_run_after_backfill_processes_nothing(mock_supabase_client):
  """
  Ticket Requirement Check: Verifies that an incremental run immediately 
  following a successful execution does not reprocess already completed data.
  """
  today = datetime.now(timezone.utc).date()
  yesterday = today - timedelta(days=1)
  yesterday_iso = datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc).isoformat()

  mock_city_response = MagicMock()
  mock_city_response.data = [{"id": "city-uuid-raleigh-999"}]

  # Mock pipeline_runs indicating a successful run completed yesterday
  mock_run_response = MagicMock()
  mock_run_response.data = [{"created_at": yesterday_iso, "status": "SUCCESS"}]

  # Mock gold_air_data showing 24 complete records for yesterday
  mock_data = [
      {"date_time": f"{yesterday.strftime('%Y-%m-%d')}T{h:02d}:00:00+00:00"} 
      for h in range(24)
  ]
  mock_data_response = MagicMock()
  mock_data_response.data = mock_data

  def table_side_effect(table_name):
    table_mock = MagicMock()
    if table_name == "gold_cities":
      table_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_city_response
    elif table_name == "pipeline_runs":
      table_mock.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_run_response
    elif table_name == "gold_air_data":
      table_mock.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = mock_data_response
    return table_mock

  mock_supabase_client.table.side_effect = table_side_effect

  planner = AirPollutionPlanner(
      cities=["Raleigh"],
      mode="incremental",
      supabase_client=mock_supabase_client
  )

  plan = planner.create_execution_plan()

  # Zero missing dates returned, proving no reprocessing
  assert plan == []


@pytest.mark.unit
def test_planner_partial_gaps_and_incomplete_days(mock_supabase_client):
  """Test that incomplete days (< 24 records) and completely missing days are caught."""
  today = datetime.now(timezone.utc).date()
  yesterday = today - timedelta(days=1)
  yesterday_str = yesterday.strftime("%Y-%m-%d")

  day_before = today - timedelta(days=2)
  day_before_str = day_before.strftime("%Y-%m-%d")

  # 1. Mock response for gold_cities lookup
  mock_city_response = MagicMock()
  mock_city_response.data = [{"id": "city-uuid-tokyo-789"}]

  # 2. Mock response for gold_air_pollution_hourly records
  mock_data = []
  # Yesterday has a full 24 records (Complete)
  for hour in range(24):
    mock_data.append({"date_time": f"{yesterday_str}T{hour:02d}:00:00+00:00"})

  # Day before yesterday has only 10 records (Incomplete / corrupt load)
  for hour in range(10):
    mock_data.append({"date_time": f"{day_before_str}T{hour:02d}:00:00+00:00"})

  mock_data_response = MagicMock()
  mock_data_response.data = mock_data


  def table_side_effect(table_name):
    table_mock = MagicMock()
    if table_name == "gold_cities":
      table_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_city_response
    elif table_name == "gold_air_data":
      table_mock.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = mock_data_response
    elif table_name == "pipeline_runs":
      table_mock.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    return table_mock

  mock_supabase_client.table.side_effect = table_side_effect

  planner = AirPollutionPlanner(cities=["Tokyo"], mode='backfill', window_days=2, supabase_client=mock_supabase_client)
  plan = planner.create_execution_plan()

  assert len(plan) == 1
  assert plan[0]["city_name"] == "tokyo"
  assert plan[0]["city_id"] == "city-uuid-tokyo-789"

  missing_dates = plan[0]["missing_dates"]

  # Yesterday should NOT be in missing dates (it had 24 records)
  assert yesterday_str not in missing_dates

  # Day before yesterday SHOULD be in missing dates (it only had 10 records)
  assert day_before_str in missing_dates


@pytest.mark.unit
def test_planner_validation_guards(mock_supabase_client):
  """Test __init__ parameter validation for cities, mode, window_days, and chunk_size."""
  with pytest.raises(ValueError, match="A list of cities must be provided"):
    AirPollutionPlanner(cities=[], supabase_client=mock_supabase_client)

  with pytest.raises(ValueError, match="A list of cities must be provided"):
    AirPollutionPlanner(cities=["   "], supabase_client=mock_supabase_client)

  with pytest.raises(ValueError, match="Pipeline mode must be either"):
    AirPollutionPlanner(cities=["New York"], mode="invalid_mode", supabase_client=mock_supabase_client)

  with pytest.raises(ValueError, match="window_days must be at least 1"):
    AirPollutionPlanner(cities=["New York"], window_days=0, supabase_client=mock_supabase_client)

  with pytest.raises(ValueError, match="chunk_size must be between 1 and 40"):
    AirPollutionPlanner(cities=["New York"], chunk_size=0, supabase_client=mock_supabase_client)

  with pytest.raises(ValueError, match="chunk_size must be between 1 and 40"):
    AirPollutionPlanner(cities=["New York"], chunk_size=45, supabase_client=mock_supabase_client)


@pytest.mark.unit
def test_planner_single_expected_dates_query_and_batch_slicing(mock_supabase_client):
  """
  Verifies that:
  1. pipeline_runs is only queried ONCE across multiple cities (no N+1 query).
  2. max_dates_per_city slices the oldest dates first in ascending chronological order.
  """
  today = datetime.now(timezone.utc).date()
  three_days_ago = today - timedelta(days=3)
  three_days_ago_iso = datetime.combine(three_days_ago, datetime.min.time(), tzinfo=timezone.utc).isoformat()

  # Uncached cities return empty data from gold_cities (city_id = None)
  mock_city_response = MagicMock(data=[])
  mock_run_response = MagicMock(data=[{"created_at": three_days_ago_iso, "status": "SUCCESS"}])

  pipeline_runs_mock = MagicMock()
  pipeline_runs_mock.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_run_response

  def table_side_effect(table_name):
    if table_name == "gold_cities":
      m = MagicMock()
      m.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_city_response
      return m
    elif table_name == "pipeline_runs":
      return pipeline_runs_mock
    return MagicMock()

  mock_supabase_client.table.side_effect = table_side_effect

  planner = AirPollutionPlanner(
      cities=["New York", "Chicago"],
      mode="incremental",
      supabase_client=mock_supabase_client
  )
  plan = planner.create_execution_plan(max_dates_per_city=2)

  # Even with 2 cities, pipeline_runs is only queried ONCE
  assert pipeline_runs_mock.select.call_count == 1

  # Both cities should have the oldest 2 dates from the 3-day window, sorted chronologically
  expected_first_two = [
      (today - timedelta(days=3)).strftime("%Y-%m-%d"),
      (today - timedelta(days=2)).strftime("%Y-%m-%d"),
  ]
  assert len(plan) == 2
  assert plan[0]["missing_dates"] == expected_first_two
  assert plan[1]["missing_dates"] == expected_first_two