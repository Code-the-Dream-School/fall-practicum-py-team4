import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(Path(__file__).resolve().parents[3] / '.env')

PAGE_SIZE = 500
FIELDS = ('id,city_id,date_time,aqi,sentiment_label,pm2_5,co,no2,'
          'aqi_rolling_7d,pm2_5_rolling_7d,llm_response,retrieve_date')


@st.cache_resource
def get_supabase_client():
    return create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])


@st.cache_data(ttl=300)
def get_cities():
    return (get_supabase_client().table('gold_cities')
            .select('id,city,state,country').order('city').execute().data)


def fetch_air_data(client, city_id):
    records = []
    offset = 0
    while True:
        page = (client.table('gold_air_data').select(FIELDS)
                .eq('city_id', city_id).order('date_time', desc=True)
                .order('id', desc=True).range(offset, offset + PAGE_SIZE - 1)
                .execute().data)
        records.extend(page)
        if not page or len(page) < PAGE_SIZE:
            break
        offset += len(page)
    return records


@st.cache_data(ttl=300)
def get_air_data(city_id):
    return fetch_air_data(get_supabase_client(), city_id)
