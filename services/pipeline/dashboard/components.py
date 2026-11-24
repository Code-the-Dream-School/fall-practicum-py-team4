import pandas as pd
import streamlit as st

from charts import METRICS

COLORS = {'Good': '#16834a', 'Fair': '#709b32', 'Moderate': '#b58900',
          'Poor': '#e56b16', 'Very Poor': '#d32f2f'}


def render_city_selector(cities):
    labels = {
        c['id']: ', '.join(
            str(c[k]).title() if k == 'city' else str(c[k])
            for k in ('city', 'state', 'country')
            if c.get(k)
        )
        for c in cities
    }   
    return st.selectbox('City', list(labels), format_func=labels.get)


def render_latest_metrics(record):
    st.subheader('Latest air quality measurements')
    columns = st.columns(4)
    for col, (label, field) in zip(columns, [('AQI', 'aqi'), ('PM2.5', 'pm2_5'), ('CO', 'co'), ('NO₂', 'no2')]):
        value = record[field]
        display = 'Unavailable' if pd.isna(value) else (f'{value:.0f} / 5' if field == 'aqi' else f'{value:.2f}')
        with col:
            st.metric(label if field == 'aqi' else f'{label} (µg/m³)', display)
            if field == 'aqi':
                sentiment = record.get('sentiment_label')
                if sentiment in COLORS:
                    st.markdown(f'<span style="color:{COLORS[sentiment]};font-weight:600">{sentiment}</span>', unsafe_allow_html=True)
    st.caption(f"Latest observation: {record['date_time']:%Y-%m-%d %H:%M} UTC")


def render_filters():
    st.subheader('Filters')
    metric = st.selectbox('Pollution metric', list(METRICS))
    days = st.selectbox('Time period', [7, 14, 30, 60], format_func=lambda n: f'Last {n} days')
    granularity = st.selectbox('Granularity', ['Hourly', 'Daily'], index=1)
    rolling = st.checkbox(
        '7-day rolling average',
        value=True
    ) if METRICS[metric][2] else False
    return metric, days, granularity, rolling


def render_summary(record):
    st.subheader('Latest air quality summary')
    summary = record.get('llm_response')
    if isinstance(summary, str) and summary.strip():
        st.text(summary.strip())
    else:
        st.info('A summary is not yet available for the latest observation.')
