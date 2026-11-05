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
    return table_mock

  mock_supabase_client.table.side_effect = table_side_effect

  planner = AirPollutionPlanner(
      cities=["Bogota"], supabase_client=mock_supabase_client
  )
  plan = planner.create_execution_plan()

  # Assertions
  assert len(plan) == 1
  assert plan[0]["city_name"] == "bogota"
  assert plan[0]["city_id"] == "city-uuid-bogota-123"

  # The window is 60 days up to yesterday
  expected_window_size = 60
  assert len(plan[0]["missing_dates"]) == expected_window_size


@pytest.mark.unit
def test_planner_incremental_mode_up_to_date(mock_supabase_client):
  """Test incremental mode with city_id: when all dates have >= 24 records, plan is empty."""
  today = datetime.now(timezone.utc).date()
  start_window = today - timedelta(days=60)
  end_window = today - timedelta(days=1)

  mock_city_response = MagicMock()
  mock_city_response.data = [{"id": "city-uuid-london-456"}]

  # Generate 24 records for every single day in the 60-day window
  mock_data = []
  current_dt = start_window
  while current_dt <= end_window:
    date_str = current_dt.strftime("%Y-%m-%d")
    for hour in range(24):
      mock_data.append({"date_time": f"{date_str}T{hour:02d}:00:00+00:00"})
    current_dt += timedelta(days=1)

  mock_data_response = MagicMock()
  mock_data_response.data = mock_data

  def table_side_effect(table_name):
    table_mock = MagicMock()
    if table_name == "gold_cities":
      table_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_city_response
    elif table_name == "gold_air_data":
      table_mock.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = mock_data_response
    return table_mock

  mock_supabase_client.table.side_effect = table_side_effect

  planner = AirPollutionPlanner(
      cities=["London"], supabase_client=mock_supabase_client
  )
  plan = planner.create_execution_plan()

  # Assertions: No missing dates, execution plan should be empty
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

  # Configure table routing behavior on the mock client
  def table_side_effect(table_name):
    table_mock = MagicMock()
    if table_name == "gold_cities":
      table_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_city_response
    elif table_name == "gold_air_data":
      table_mock.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = mock_data_response
    return table_mock

  mock_supabase_client.table.side_effect = table_side_effect

  planner = AirPollutionPlanner(
      cities=["Tokyo"], window_days=2, supabase_client=mock_supabase_client
  )
  plan = planner.create_execution_plan()

  assert len(plan) == 1
  assert plan[0]["city_name"] == "tokyo"
  assert plan[0]["city_id"] == "city-uuid-tokyo-789"

  missing_dates = plan[0]["missing_dates"]

  # Yesterday should NOT be in missing dates (it had 24 records)
  assert yesterday_str not in missing_dates

  # Day before yesterday SHOULD be in missing dates (it only had 10 records)
  assert day_before_str in missing_dates