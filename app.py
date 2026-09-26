import streamlit as st
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import math
import json

# ========== 【最重要！必须放在所有streamlit代码最前面】 ==========
st.set_page_config(page_title="广州地铁赶车计算器", layout="wide")

# ===================== 加载地铁数据库（适配【线路顶层】JSON） =====================
with open("metro_data.json", "r", encoding="utf-8") as f:
    line_data = json.load(f)

# ===================== 【广州地铁 各线路真实历史发车间隔配置】 =====================
# 格式："线路名": {"peak":高峰间隔(分钟), "offpeak":平峰间隔(分钟)}
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

# 进站固定耗时（从进入地铁站入口到走到月台，单位秒）
STATION_ENTER_TO_PLATFORM_SEC = 120

# 预构建：全部站点字典（站名 -> 归属线路 + 站点信息，用于定位找最近站）
station_all = {}
for line_name, line_info in line_data.items():
    for st_info in line_info["stations"]:
        station_name = st_info["station_name"]
        # 换乘站：同一个站点会存在多条线路
        if station_name not in station_all:
            station_all[station_name] = {
                "lines": {}
            }
        station_all[station_name]["lines"][line_name] = st_info
        station_all[station_name]["lat"] = st_info["lat"]
        station_all[station_name]["lon"] = st_info["lon"]

# 三档步行速度配置
speed_map = {
    "悠悠慢走": 0.8,
    "正常步行": 1.2,
    "小步快跑": 1.8
}

# 节假日列表（月-日）
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
    """球面距离计算，单位米"""
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
    """
    站点模糊搜索：纯汉字包含匹配，不需要pypinyin库
    输入"鹅岭"就能匹配飞鹅岭，自动去除多余空格
    """
    kw = keyword.strip()
    if not kw:
        return all_station_list
    result = []
    for name in all_station_list:
        if kw in name:
            result.append(name)
    return result

def get_beijing_now():
    """唯一基准后台北京时间"""
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

# 根据当前时间 + 线路，自动获取真实发车间隔
def get_line_interval(line_name:str, now_dt:datetime):
    month_day = now_dt.strftime("%m-%d")
    is_holiday = month_day in holiday_list
    weekday = now_dt.weekday()
    hour = now_dt.hour
    minute = now_dt.minute
    is_weekend = weekday >=5

    # 找不到线路配置默认4分钟
    cfg = line_interval_config.get(line_name, {"peak":2, "offpeak":4})
    if is_holiday or is_weekend:
        return cfg["offpeak"]
    #工作日早晚高峰
    is_morning_rush = (7 <= hour <=9)
    is_evening_rush = (17 <= hour <=19 and minute <=30)
    if is_morning_rush or is_evening_rush:
        return cfg["peak"]
    else:
        return cfg["offpeak"]

def time_str_to_beijing_datetime(timestr: str, ref_dt: datetime):
    if not timestr or timestr.strip() == "":
        raise ValueError("首末班时间为空，请检查json数据")
    parts = timestr.strip().split(":")
    if len(parts) !=2:
        raise ValueError(f"时间格式错误「{timestr}」，需要HH:MM")
    h, m = map(int, parts)
    return datetime(ref_dt.year, ref_dt.month, ref_dt.day, h, m, tzinfo=ZoneInfo("Asia/Shanghai"))

# 生成当日模拟班次（基于首末班 + 自动获取线路高峰/平峰间隔）
def gen_train_schedule(first_time:str, last_time:str, interval_min:float, ref_dt:datetime):
    try:
        trains = []
        t_start = time_str_to_beijing_datetime(first_time, ref_dt)
        t_end = time_str_to_beijing_datetime(last_time, ref_dt)
        current = t_start
        while current <= t_end:
            trains.append(current.strftime("%H:%M"))
            current += timedelta(minutes=interval_min)
        return trains
    except Exception as e:
        st.error(f"班次生成失败：{e}")
        return []

def filter_train_schedule(train_time_str_list, now_beijing, arrive_platform_dt):
    train_list = []
    for t_str in train_time_str_list:
        dt = time_str_to_beijing_datetime(t_str, now_beijing)
        train_list.append((t_str, dt))
    missed = []
    risky = []
    available = []
    for t_str, dt in train_list:
        if dt < now_beijing:
            missed.append((t_str, dt))
        elif dt < arrive_platform_dt:
            risky.append((t_str, dt))
        else:
            available.append((t_str, dt))
    latest_miss = missed[-1] if missed else None
    latest_risky = risky[0] if risky else None
    first_available = available[0] if available else None
    second_available = available[1] if len(available)>=2 else None
    has_future = len(risky) >0 or len(available) >0
    return latest_miss, latest_risky, first_available, second_available, has_future

# ===================== Streamlit页面 =====================

# 前端JS时钟（仅页面展示，不参与计算）
st.components.v1.html("""
<script>
setInterval(() => {
    const now = new Date();
    const beijing = new Date(now.toLocaleString("en-US", {timeZone: "Asia/Shanghai"}));
    const y = beijing.getFullYear();
    const m = String(beijing.getMonth() + 1).padStart(2, '0');
    const d = String(beijing.getDate()).padStart(2, '0');
    const hh = String(beijing.getHours()).padStart(2, '0');
    const mm = String(beijing.getMinutes()).padStart(2, '0');
    const ss = String(beijing.getSeconds()).padStart(2, '0');
    document.getElementById("beijing-time").innerText =
        `🕒 北京时间：${y}-${m}-${d} ${hh}:${mm}:${ss}`;
}, 1000);
</script>
<div id="beijing-time" style="font-size:32px; font-weight:bold;"></div>
""", height=70)

# 定位JS，定位成功自动刷新页面
st.components.v1.html("""
<script>
if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(pos => {
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        window.localStorage.setItem("geo_lat", lat);
        window.localStorage.setItem("geo_lon", lon);
        window.location.reload();
    }, err => {
        console.log("定位失败", err);
    });
}
</script>
""", height=0)

# Session初始化
if "selected_line" not in st.session_state:
    st.session_state["selected_line"] = list(line_data.keys())[0]

# 自动刷新开关
auto_refresh = st.checkbox("开启60秒自动刷新（后台重新计算班次）", value=False)
if auto_refresh:
    st.components.v1.html("""<script>setInterval(()=>window.location.reload(),60000);</script>""", height=0)
else:
    st.caption("自动刷新已关闭，修改参数才更新结果")

now = get_beijing_now()
st.divider()

# ========== 定位模块 ==========
col_loc1, col_loc2 = st.columns([1,1])
with col_loc1:
    use_loc = st.checkbox("使用浏览器定位，自动选择最近站点", value=False)
with col_loc2:
    st.info("定位成功页面自动刷新；公网部署需要HTTPS才能启用定位")

# ========== 线路选择 ==========
line_list = list(line_data.keys())
selected_line = st.selectbox("【1】选择地铁线路", line_list, index=line_list.index(st.session_state["selected_line"]))
st.session_state["selected_line"] = selected_line
line_info = line_data[selected_line]
st.markdown(f"**{line_info['name']} | {line_info['desc']}**")

# ========== 模糊搜索站点（无pypinyin，汉字搜索） ==========
search_key = st.text_input("🔍 模糊搜索站点（输入站点部分汉字，例：鹅岭 搜飞鹅岭）", "")
all_station_names = list(station_all.keys())
matched_stations = fuzzy_search_station(search_key, all_station_names)

# 站点下拉框，只展示匹配到的站点
if matched_stations:
    selected_station = st.selectbox("【2】选择站点", matched_stations)
else:
    st.warning("未找到匹配站点，请修改关键词")
    selected_station = ""

# 定位模式覆盖站点选择 & 自动计算距离
walk_distance = 200.0
user_lat = None
user_lon = None
if use_loc:
    st.warning("浏览器弹出权限请求，请【允许位置】，定位成功页面自动刷新")
    col_lat, col_lon = st.columns(2)
    with col_lat:
        lat_input = st.number_input("纬度", value=23.13, format="%.4f")
    with col_lon:
        lon_input = st.number_input("经度", value=113.31, format="%.4f")
    user_lat = lat_input
    user_lon = lon_input
    nearest_station_name, dist = find_nearest_station(lat_input, lon_input)
    st.success(f"✅ 根据坐标计算，最近站点：【{nearest_station_name}】，直线距离 {dist:.0f} 米")
    selected_station = nearest_station_name
    walk_distance = dist  # 自动赋值距离，不需要手动输入

# 获取当前选中站点的全部信息（处理换乘站）
if selected_station:
    station_meta = station_all[selected_station]
    station_line_names = list(station_meta["lines"].keys())
    if len(station_line_names) > 1:
        st.info(f"✅ {selected_station} 是换乘站，请选择线路")
        selected_line = st.selectbox("选择该站点的线路", station_line_names)
    else:
        selected_line = station_line_names[0]
    station_info = station_meta["lines"][selected_line]

    # ========== 自动读取当前线路真实间隔 ==========
    current_interval = get_line_interval(selected_line, now)
    st.subheader("🚇 班次信息")
    st.markdown(f"当前线路：**{selected_line}**，当前时段自动发车间隔：**{current_interval} 分钟**")

    # 【核心改动】定位开启时隐藏距离输入框；关闭定位才允许手动输入
    if not use_loc:
        walk_distance = st.number_input("当前位置 → 地铁站入口 的步行距离（米）", min_value=0.0, value=200.0, step=10.0)
    else:
        st.markdown(f"📏 当前位置到【{selected_station}】估算步行距离：**{walk_distance:.0f} 米（定位自动计算，不可手动修改）**")

    speed_label = st.selectbox("步行速度", list(speed_map.keys()), index=1)
    walk_speed = speed_map[speed_label]

    # 后台时间计算全部基于now
    auto_security_min = get_auto_security_time(now)
    auto_security_sec = auto_security_min * 60
    walk_to_entrance_sec = walk_distance / walk_speed
    # 总耗时 = 走到入口 + 进站到月台固定耗时 + 安检
    total_need_sec = walk_to_entrance_sec + STATION_ENTER_TO_PLATFORM_SEC + auto_security_sec
    arrive_platform_time = now + timedelta(seconds=total_need_sec)

    st.subheader("📋 时间预估")
    st.write(f"走到地铁站入口耗时：{walk_to_entrance_sec/60:.1f} 分钟")
    st.write(f"进站步行至月台固定耗时：{STATION_ENTER_TO_PLATFORM_SEC/60:.1f} 分钟")
    st.write(f"🔍 安检预估：{auto_security_min:.1f} 分钟（根据时段/周末/节假日动态计算）")
    st.write(f"✅ 预计到达月台时间：{arrive_platform_time.strftime('%H:%M:%S')}")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("⬆️ dirA 方向（上行）")
        up_trains = gen_train_schedule(station_info["dirA_first"], station_info["dirA_last"], current_interval, now)
        latest_miss, latest_risky, first_available, second_available, has_future = filter_train_schedule(
            up_trains, now, arrive_platform_time
        )
        if latest_miss:
            t_str, dt = latest_miss
            st.error(f"❌ 最近已错过：{t_str}")
        if latest_risky:
            t_str, dt = latest_risky
            remain_min = (dt - now).total_seconds() / 60
            st.warning(f"⚠️ 有可能错过：{t_str}，距离到站还有 {remain_min:.1f} 分钟")
        if first_available:
            t_str, dt = first_available
            remain_min = (dt - arrive_platform_time).total_seconds() / 60
            st.success(f"✅ 可以赶上：{t_str}，到站后剩余 {remain_min:.1f} 分钟")
        if second_available:
            t_str, dt = second_available
            remain_min = (dt - arrive_platform_time).total_seconds() / 60
            st.info(f"📌 备选班次：{t_str}，到站后剩余 {remain_min:.1f} 分钟")
        if not has_future:
            st.warning("⚠️ 当前时段暂无后续列车")

    with col2:
        st.subheader("⬇️ dirB 方向（下行）")
        down_trains = gen_train_schedule(station_info["dirB_first"], station_info["dirB_last"], current_interval, now)
        latest_miss, latest_risky, first_available, second_available, has_future = filter_train_schedule(
            down_trains, now, arrive_platform_time
        )
        if latest_miss:
            t_str, dt = latest_miss
            st.error(f"❌ 最近已错过：{t_str}")
        if latest_risky:
            t_str, dt = latest_risky
            remain_min = (dt - now).total_seconds() / 60
            st.warning(f"⚠️ 有可能错过：{t_str}，距离到站还有 {remain_min:.1f} 分钟")
        if first_available:
            t_str, dt = first_available
            remain_min = (dt - arrive_platform_time).total_seconds() / 60
            st.success(f"✅ 可以赶上：{t_str}，到站后剩余 {remain_min:.1f} 分钟")
        if second_available:
            t_str, dt = second_available
            remain_min = (dt - arrive_platform_time).total_seconds() / 60
            st.info(f"📌 备选班次：{t_str}，到站后剩余 {remain_min:.1f} 分钟")
        if not has_future:
            st.warning("⚠️ 当前时段暂无后续列车")

st.divider()
st.caption("说明：时刻表由首末班+线路历史高峰/平峰间隔自动生成；直线距离为估算，实际步行道路距离会更长；所有逻辑计算使用Python后台北京时间。定位+模糊搜索双重站点选择。")
