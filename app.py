import streamlit as st
from datetime import datetime
import json
from geopy.distance import geodesic

# ---------------------- 加载外部json站点文件 ----------------------
@st.cache_data
def load_metro_json():
    with open("metro_data.json", "r", encoding="utf-8") as f:
        return json.load(f)

metro_data = load_metro_json()

# 收集全部站点，用于距离计算
all_stations = []
for line_name, line_info in metro_data.items():
    for st_info in line_info["stations"]:
        all_stations.append({
            "line": line_name,
            "name": st_info["station_name"],
            "lat": st_info["lat"],
            "lon": st_info["lon"]
        })

# ---------------------- 页面头部 ----------------------
st.title("广州地铁赶车预估工具")
now = datetime.now()
st.subheader(f"🕒 当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')}")

# ---------------------- 步行参数选择 ----------------------
st.sidebar.header("步行参数设置")
walk_speed_kmh = st.sidebar.selectbox(
    "步行速度",
    options=[3.0, 4.0, 5.0],
    format_func=lambda x: f"{x} km/h",
    index=1  # 默认4km/h
)
road_correct = 1.3  # 道路绕行修正系数，直线距离 ×1.3

# ---------------------- 获取当前位置 ----------------------
st.subheader("📍 获取当前位置")
# JS定位组件
loc_js = """
<script>
navigator.geolocation.getCurrentPosition(
    function(pos) {
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        document.getElementById("lat_out").innerText = lat;
        document.getElementById("lon_out").innerText = lon;
    },
    function(err) {
        document.getElementById("lat_out").innerText = "fail";
        document.getElementById("lon_out").innerText = "fail";
    }
)
</script>
<div>纬度：<span id="lat_out"></span></div>
<div>经度：<span id="lon_out"></span></div>
"""
st.components.v1.html(loc_js, height=120)

col1, col2 = st.columns(2)
with col1:
    input_lat = st.text_input("手动输入纬度", value="")
with col2:
    input_lon = st.text_input("手动输入经度", value="")

user_lat = None
user_lon = None
if input_lat and input_lon:
    try:
        user_lat = float(input_lat)
        user_lon = float(input_lon)
    except:
        st.warning("坐标格式错误")

# ---------------------- 计算最近地铁站 ----------------------
if user_lat and user_lon:
    st.subheader("🚇 附近地铁站（预估步行时间）")
    station_list = []
    for s in all_stations:
        dist_straight = geodesic((user_lat, user_lon), (s["lat"], s["lon"])).meters
        dist_road = dist_straight * road_correct
        # 步行耗时 分钟
        walk_min = dist_road / (walk_speed_kmh * 1000 / 60)
        station_list.append({
            "线路": s["line"],
            "站点": s["name"],
            "直线距离(m)": round(dist_straight, 1),
            "预估步行距离(m)": round(dist_road, 1),
            "预估步行分钟": round(walk_min,1)
        })
    # 按步行距离排序
    station_list.sort(key=lambda x: x["预估步行分钟"])
    # 展示前5个
    for s in station_list[:5]:
        st.write(f"{s['线路']} | {s['站点']} | 预估步行：{s['预估步行分钟']} 分钟")

# ---------------------- 线路 & 上下行时刻表查询 ----------------------
st.divider()
st.subheader("📋 线路到站时刻表查询")
line_select = st.selectbox("选择地铁线路", list(metro_data.keys()))
line_data = metro_data[line_select]
dir_opt = st.radio("选择方向", ["上行(dirA)", "下行(dirB)"])

# 渲染时刻表
st.write(f"### {line_select} - {dir_opt}")
table_rows = []
for station in line_data["stations"]:
    if dir_opt == "上行(dirA)":
        first = station["dirA_first"]
        last = station["dirA_last"]
    else:
        first = station["dirB_first"]
        last = station["dirB_last"]
    table_rows.append({
        "站点": station["station_name"],
        "首班车": first,
        "末班车": last
    })
st.table(table_rows)

