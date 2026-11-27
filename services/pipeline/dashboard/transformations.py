import pandas as pd

METRIC_COLUMNS = ['aqi', 'pm2_5', 'co', 'no2', 'aqi_rolling_7d', 'pm2_5_rolling_7d']


def prepare_air_data(records):
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df['date_time'] = pd.to_datetime(df['date_time'], utc=True, errors='coerce', format='mixed')
    for column in METRIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors='coerce')
    return df.dropna(subset=['date_time']).sort_values(['date_time', 'id']).reset_index(drop=True)


def filter_date_range(df, days):
    if df.empty:
        return df.copy()
    end = df['date_time'].max()
    return df.loc[df['date_time'] > end - pd.Timedelta(days=days)].copy()


def aggregate_data(df, granularity):
    if df.empty:
        return df.copy()
    regular = ['aqi', 'pm2_5', 'co', 'no2']
    rolling = ['aqi_rolling_7d', 'pm2_5_rolling_7d']
    indexed = df.sort_values(['date_time', 'id']).set_index('date_time')
    freq = 'D' if granularity == 'Daily' else 'h'
    means = indexed[regular].resample(freq).mean()
    # Keep the stored rolling values from the final observation in each bin,
    # including nulls; never average a rolling average again.
    last = indexed[rolling].groupby(pd.Grouper(freq=freq)).agg(
        lambda values: values.iloc[-1] if len(values) else float('nan')
    )
    return means.join(last).reset_index()
