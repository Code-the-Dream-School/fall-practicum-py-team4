import streamlit as st
import logging

from database import get_cities, get_air_data
from transformations import prepare_air_data, filter_date_range, aggregate_data
from charts import create_time_series
from components import render_city_selector, render_latest_metrics, render_filters, render_summary

logger = logging.getLogger(__name__)

def main():
    st.set_page_config(page_title='City Air Tracker', layout='wide')
    title_col, city_col = st.columns([3, 1])
    with title_col:
        st.title('City Air Tracker')
        st.caption('Air pollution monitoring and historical analysis')
    try:
        cities = get_cities()

        if not cities:
            st.info('No cities available.')
            return

        with city_col:
            city_id = render_city_selector(cities)

        df = prepare_air_data(get_air_data(city_id))

    except Exception:
        logger.exception('Failed to load air quality data')
        st.error('Unable to load air quality data. Check the database configuration and connection.')
        return

    if df.empty:
        st.info('No observations available for this city.')
        return 
    
    latest = df.iloc[-1]
    st.divider()
    render_latest_metrics(latest)
    st.divider()
    st.subheader('Historical air pollution trends')
    chart_col, filter_col = st.columns([4, 1])
    with filter_col:
        metric, days, granularity, rolling = render_filters()
    with chart_col:
        filtered = filter_date_range(df, days)
        chart_data = aggregate_data(filtered, granularity)
        st.markdown(f'**{metric} — Last {days} days**')
        st.plotly_chart(create_time_series(chart_data, metric, granularity, rolling), use_container_width=True)
        st.caption(f'{len(filtered):,} hourly observations. Period ends at latest available observation; daily averages use available hours in UTC.')
    st.divider()
    render_summary(latest)


if __name__ == '__main__':
    main()
