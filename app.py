import streamlit as st
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import math
import json
from streamlit_geolocation import streamlit_geolocation

# ========== 【初始化session_state 保存定位信息，跨刷新保留】 ==========
if "user_lat" not in st.session_state:
    st.session_state.user_lat = None
if "user_lon" not in st.session_state:
    st.session_state.user_lon = None
if "nearest_station" not in st.session_state:
    st.session_state.nearest_station = None
if "distance_to_station" not in st.session_state:
    st.session_state.distance_to_station = None

# ========== 页面配置 ==========
st.set_page_config(page_title="广州地铁赶车计算器", layout="wide")

# ===================== 加载地铁数据库 =====================
with open("metro_data.json", "r", encoding="utf-8") as f:
    line_data = json.load(f)

# ===================== 线路发车间隔配置 =====================
line_interval_config = {
    "1号线": {"peak": 2, "offpeak": 4},
    "2号线": {"peak": 2, "offpeak": 3},
    "3号线": {"peak": 1.5, "offpeak": 3},
    "3号线北延段": {"peak": 2, "offpeak":4},
    "4号线": {"peak": 3, "offpeak":6},
    "5号线": {"peak": 2, "offpeak":3},
    "6号线": {"peak": 2.5, "offpeak":4},
    "7号线": {"peak": 3, "offpeak":5},
    "8号线": {"peak":2, "offpeak":3.5},
    "9号线": {"peak":4, "offpeak":6},
    "13号线": {"peak":4, "offpeak":8},
    "14号线": {"peak":5, "offpeak":8},
    "18号线": {"peak":3, "offpeak":5},
    "21号线": {"peak":4, "offpeak":7},
    "22号线": {"peak":4, "offpeak":6},
    "广佛线": {"peak":2.5, "offpeak":4},
}

# 进站固定耗时（入口走到月台）
STATION_ENTER_TO_PLATFORM_SEC = 120

# 构建全部站点字典
station_all = {}
for line_name, line_info in line_data.items():
    for st_info in line_info["stations"]:
        station_name = st_info["station_name"]
        if station_name not in station_all:
            station_all[station_name] = {
                "lines": {}
            }
        station_all[station_name]["lines"][line_name] = st_info
        station_all[station_name]["lat"] = st_info["lat"]
        station_all[station_name]["lon"] = st_info["lon"]

# 步行速度
speed_map = {
    "悠悠慢走": 0.8,
    "正常步行": 1.2,
    "小步快跑": 1.8
}

# 节假日
holiday_list = [
    "01-01",
    "01-29","01-30","01-31","02-01","02-02","02-03","02-04",
    "04-04","04-05","04-06",
    "05-01","05-02","05-03","05-04","05-05",
    "05-31","06-01","06-02",
    "10-01","10-02","10-03","10-04","10-05","10-06","10-07"
]

# ===================== 工具函数 =====================
def haversine(lat1, lon1, lat2, lon2):
    """球面距离，单位米"""
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def find_nearest_station(user_lat, user_lon):
    min_dist = float("inf")
    nearest_name = None
    for name, info in station_all.items():
        dist = haversine(user_lat, user_lon, info["lat"], info["lon"])
        if dist < min_dist:
            min_dist = dist
            nearest_name = name
    return nearest_name, min_dist

def fuzzy_search_station(keyword:str, all_station_list):
    kw = keyword.strip()
    if not kw:
        return all_station_list
    result = []
    for name in all_station_list:
        if kw in name:
            result.append(name)
    return result

def get_beijing_now():
    return datetime.now(tz=ZoneInfo("Asia/Shanghai"))

def get_auto_security_time(now_dt:datetime):
    month_day = now_dt.strftime("%m-%d")
    is_holiday = month_day in holiday_list
    weekday = now_dt.weekday()
    hour = now_dt.hour
    minute = now_dt.minute
    is_weekend = weekday >=5
    if is_holiday or is_weekend:
        return 1.5
    else:
        is_morning_rush = (7 <= hour <=9)
        is_evening_rush = (17 <= hour <=19 and minute <=30)
        if is_morning_rush or is_evening_rush:
            return 2.0
        else:
            return 1.0

def get_line_interval(line_name:str, now_dt:datetime):
    month_day = now_dt.strftime("%m-%d")
    is_holiday = month_day in holiday_list
    weekday = now_dt.weekday()
    hour = now_dt.hour
    minute = now_dt.minute
    is_weekend = weekday >=5
    cfg = line_interval_config.get(line_name, {"peak":2, "offpeak":4})
    if is_holiday or is_weekend:
        return cfg["offpeak"]
    is_morning_rush = (7 <= hour <=9)
    is_evening_rush = (17 <= hour <=19 and minute <=30)
    if is_morning_rush or is_evening_rush:
        return cfg["peak"]
    else:
        return cfg["offpeak"]

def time_str_to_datetime(timestr: str, ref_dt: datetime):
    if not timestr or timestr.strip() == "":
        raise ValueError("时间为空")
    parts = timestr.strip().split(":")
    h, m = map(int, parts)
    return datetime(ref_dt.year, ref_dt.month, ref_dt.day, h, m, tzinfo=ZoneInfo("Asia/Shanghai"))

def gen_train_schedule(first_time:str, last_time:str, interval_min:float, ref_dt:datetime):
    trains = []
    t_start = time_str_to_datetime(first_time, ref_dt)
    t_end = time_str_to_datetime(last_time, ref_dt)
    current = t_start
    while current <= t_end:
        trains.append(current.strftime("%H:%M"))
        current += timedelta(minutes=interval_min)
    return trains

def filter_train(train_list, now, arrive_platform):
    train_data = []
    for t in train_list:
        dt = time_str_to_datetime(t, now)
        train_data.append((t, dt))
    missed = []
    risky = []
    available = []
    for t_str, dt in train_data:
        if dt < now:
            missed.append((t_str, dt))
        elif dt < arrive_platform:
            risky.append((t_str, dt))
        else:
            available.append((t_str, dt))
    latest_miss = missed[-1] if missed else None
    risky_next = risky[0] if risky else None
    first_ok = available[0] if available else None
    second_ok = available[1] if len(available)>=2 else None
    has_future = len(risky) or len(available)
    return latest_miss, risky_next, first_ok, second_ok, has_future

# ===================== UI页面 =====================
# 北京时间显示
now = get_beijing_now()
st.markdown(f"# 🕒 当前北京时间：{now.strftime('%Y-%m-%d %H:%M:%S')}")
st.divider()

# 定位按钮
st.subheader("📍 获取当前位置")
st.info("点击下面按钮，浏览器会请求位置权限，授权后自动寻找最近地铁站（部署到streamlit.cloud HTTPS环境生效）")
location_result = streamlit_geolocation()

# 拿到定位结果，存入session_state
if location_result and location_result.get("latitude"):
    lat = location_result["latitude"]
    lon = location_result["longitude"]
    # 更新session
    st.session_state.user_lat = lat
    st.session_state.user_lon = lon
    nearest_station_name, dist = find_nearest_station(lat, lon)
    st.session_state.nearest_station = nearest_station_name
    st.session_state.distance_to_station = dist
    st.success(f"✅ 定位成功！最近站点：【{nearest_station_name}】，估算直线距离 {dist:.0f} m")

# 线路选择
line_list = list(line_data.keys())
if "selected_line" not in st.session_state:
    st.session_state["selected_line"] = line_list[0]
selected_line = st.selectbox("【1】选择地铁线路", line_list, index=line_list.index(st.session_state["selected_line"]))
st.session_state["selected_line"] = selected_line
line_info = line_data[selected_line]

# 站点搜索
search_key = st.text_input("🔍 模糊搜索站点（输入站名，例如：花都）", "")
all_station_names = list(station_all.keys())
matched_stations = fuzzy_search_station(search_key, all_station_names)

# 如果定位成功，自动选中最近站点
if st.session_state.nearest_station is not None:
    if st.session_state.nearest_station in matched_stations:
        selected_station = st.session_state.nearest_station
    else:
        selected_station = st.selectbox("【2】选择站点", matched_stations) if matched_stations else ""
else:
    selected_station = st.selectbox("【2】选择站点", matched_stations) if matched_stations else ""

# 站点信息处理
walk_distance = 200.0
if selected_station:
    station_meta = station_all[selected_station]
    station_line_names = list(station_meta["lines"].keys())
    if len(station_line_names) >1:
        st.info(f"✅ {selected_station} 是换乘站，请选择对应线路")
        selected_line = st.selectbox("选择该站点的线路", station_line_names)
    else:
        selected_line = station_line_names[0]
    station_info = station_meta["lines"][selected_line]

    # 班次标题
    current_interval = get_line_interval(selected_line, now)
    st.subheader("🚇 班次信息")
    st.markdown(f"当前线路：**{selected_line}**，当前时段自动发车间隔：**{current_interval} 分钟**")

    # 距离：定位成功就自动使用，否则手动输入
    if st.session_state.distance_to_station is not None:
        walk_distance = st.session_state.distance_to_station
        st.markdown(f"📏 当前位置到【{selected_station}】估算步行距离：**{walk_distance:.0f} 米（定位自动计算）**")
    else:
        walk_distance = st.number_input("当前位置 → 地铁站入口 的步行距离（米）", min_value=0.0, value=200.0, step=10.0)

    speed_label = st.selectbox("步行速度", list(speed_map.keys()), index=1)
    walk_speed = speed_map[speed_label]

    # 时间计算
    auto_security_min = get_auto_security_time(now)
    auto_security_sec = auto_security_min * 60
    walk_to_entrance_sec = walk_distance / walk_speed
    total_need_sec = walk_to_entrance_sec + STATION_ENTER_TO_PLATFORM_SEC + auto_security_sec
    arrive_platform_time = now + timedelta(seconds=total_need_sec)

    st.subheader("📋 时间预估")
    st.write(f"走到地铁站入口耗时：{walk_to_entrance_sec/60:.1f} 分钟")
    st.write(f"进站步行至月台固定耗时：{STATION_ENTER_TO_PLATFORM_SEC/60:.1f} 分钟")
    st.write(f"🔍 安检预估：{auto_security_min:.1f} 分钟")
    st.write(f"✅ 预计到达月台时间：{arrive_platform_time.strftime('%H:%M:%S')}")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("⬆️ 上行方向")
        up_trains = gen_train_schedule(station_info["dirA_first"], station_info["dirA_last"], current_interval, now)
        latest_miss, risky_next, first_ok, second_ok, has_future = filter_train(up_trains, now, arrive_platform_time)
        if latest_miss:
            st.error(f"❌ 最近已错过：{latest_miss[0]}")
        if risky_next:
            rem = (risky_next[1] - now).total_seconds()/60
            st.warning(f"⚠️ 有可能错过：{risky_next[0]}，距离到站还有 {rem:.1f} 分钟")
        if first_ok:
            rem = (first_ok[1] - arrive_platform_time).total_seconds()/60
            st.success(f"✅ 可以赶上：{first_ok[0]}，到站后剩余 {rem:.1f} 分钟")
        if second_ok:
            rem = (second_ok[1] - arrive_platform_time).total_seconds()/60
            st.info(f"📌 备选班次：{second_ok[0]}，到站后剩余 {rem:.1f} 分钟")
        if not has_future:
            st.warning("⚠️ 当前时段无后续列车")

    with col2:
        st.subheader("⬇️ 下行方向")
        down_trains = gen_train_schedule(station_info["dirB_first"], station_info["dirB_last"], current_interval, now)
        latest_miss, risky_next, first_ok, second_ok, has_future = filter_train(down_trains, now, arrive_platform_time)
        if latest_miss:
            st.error(f"❌ 最近已错过：{latest_miss[0]}")
        if risky_next:
            rem = (risky_next[1] - now).total_seconds()/60
            st.warning(f"⚠️ 有可能错过：{risky_next[0]}，距离到站还有 {rem:.1f} 分钟")
        if first_ok:
            rem = (first_ok[1] - arrive_platform_time).total_seconds()/60
            st.success(f"✅ 可以赶上：{first_ok[0]}，到站后剩余 {rem:.1f} 分钟")
        if second_ok:
            rem = (second_ok[1] - arrive_platform_time).total_seconds()/60
            st.info(f"📌 备选班次：{second_ok[0]}，到站后剩余 {rem:.1f} 分钟")
        if not has_future:
            st.warning("⚠️ 当前时段无后续列车")

st.divider()
st.caption("说明：距离为球面直线估算，实际步行道路距离会更长；部署在https域名下定位功能正常。")
