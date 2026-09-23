import streamlit as st
import openmeteo_requests
import requests_cache
import pandas as pd
from retry_requests import retry
import plotly.express as px
from datetime import date, timedelta
import requests

# 城市名称转经纬度
def get_city_lat_lon(city_name):
    geo_url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": city_name, "count": 1, "language": "zh"}
    try:
        resp = requests.get(geo_url, params=params, timeout=15)
        data = resp.json()
        if "results" not in data or len(data["results"]) == 0:
            return None, None, None
        res = data["results"][0]
        return res["name"], res["latitude"], res["longitude"]
    except Exception as e:
        return None, None, None

# 获取近一年气温
def get_weather_data(lat, lon):
    end_date = date.today()
    start_date = end_date - timedelta(days=365)

    cache_session = requests_cache.CachedSession('.cache_weather', expire_after=-1)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "daily": ["temperature_2m_max", "temperature_2m_min"],
        "timezone": "Asia/Shanghai"
    }
    responses = openmeteo.weather_api(url, params=params)
    response = responses[0]

    daily = response.Daily()
    daily_dates = pd.date_range(
        start=pd.to_datetime(daily.Time(), unit="s"),
        end=pd.to_datetime(daily.TimeEnd(), unit="s"),
        freq=pd.Timedelta(seconds=daily.Interval()),
        inclusive="left"
    )
    daily_max_temp = daily.Variables(0).ValuesAsNumpy()
    daily_min_temp = daily.Variables(1).ValuesAsNumpy()

    df = pd.DataFrame({
        "date": daily_dates,
        "最高气温": daily_max_temp,
        "最低气温": daily_min_temp
    })
    return df, start_date, end_date

# ---------------------- Streamlit页面 ----------------------
st.set_page_config(page_title="气温查询", layout="wide")
st.title("🌡️ 城市近一年气温查询")

city_input = st.text_input("请输入城市名称", value="广州")
btn = st.button("查询气温并绘图")

if btn:
    city_real_name, lat, lon = get_city_lat_lon(city_input)
    if lat is None:
        st.error("找不到该城市，请更换城市名称！")
    else:
        st.info(f"已识别城市：{city_real_name}，正在获取数据...")
        df, s_date, e_date = get_weather_data(lat, lon)
        st.success("数据获取成功！")

        fig = px.line(
            df,
            x="date",
            y=["最高气温", "最低气温"],
            title=f"{city_real_name} 近一年气温变化 {s_date} ~ {e_date}",
            labels={"date": "日期", "value": "气温 ℃"}
        )
        fig.update_traces(selector={"name":"最高气温"}, line_color="#e74c3c")
        fig.update_traces(selector={"name":"最低气温"}, line_color="#3498db")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("查看原始气温数据表"):
            st.dataframe(df)