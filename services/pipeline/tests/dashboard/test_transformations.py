import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dashboard'))
from transformations import prepare_air_data, filter_date_range, aggregate_data, METRIC_COLUMNS


def records():
    return [dict(id=i, date_time=t.isoformat(), **{k: i for k in METRIC_COLUMNS})
            for i, t in enumerate(pd.date_range('2026-11-01', periods=1440, freq='h', tz='UTC'))]


def test_prepare_and_filter():
    df = prepare_air_data(records()[::-1])
    assert df['date_time'].is_monotonic_increasing
    assert len(filter_date_range(df, 7)) == 168
    assert len(filter_date_range(df, 60)) == 1440


def test_daily_average():
    df = aggregate_data(prepare_air_data(records()), 'Daily')
    assert len(df) == 60
    assert df.iloc[0]['co'] == 11.5


def test_missing_hour():
    rows = records()[:3]
    df = aggregate_data(prepare_air_data([rows[0], rows[2]]), 'Hourly')
    assert pd.isna(df.iloc[1]['aqi'])


def test_empty():
    assert prepare_air_data([]).empty


def test_daily_rolling_uses_last_observation():
    df = aggregate_data(prepare_air_data(records()[:24]), 'Daily')
    assert df.iloc[0]['aqi_rolling_7d'] == 23
    assert df.iloc[0]['pm2_5_rolling_7d'] == 23


def test_daily_rolling_preserves_last_null():
    rows = records()[:24]
    rows[-1]['aqi_rolling_7d'] = None
    df = aggregate_data(prepare_air_data(rows), 'Daily')
    assert pd.isna(df.iloc[0]['aqi_rolling_7d'])
