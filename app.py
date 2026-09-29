from datetime import datetime, timedelta
import pandas as pd
import pytz
import requests
import streamlit as st
from streamlit_js_eval import get_geolocation
import urllib3

# 關閉不安全 HTTPS 請求的 SSL 警告訊息
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 頁面基本設定
st.set_page_config(
    page_title="全臺港口動態過灘與 UKC 評估系統 (API 即時版)",
    page_icon="🚢",
    layout="centered",
)

# 時區設定（台灣時間）
tw_tz = pytz.timezone("Asia/Taipei")
now = datetime.now(tw_tz)

st.title("🚢 全臺港口動態過灘與 UKC 評估系統")
st.caption(
    f"📅 當前時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (CST) ｜ 資料來源：中央氣象署 API 即時資料"
)

# --- 1. 全臺灣主要港口與氣象署對應縣市名稱 ---
TAIWAN_PORTS = {
    "高雄港第二航道": {
        "depth": 17.0,
        "cwa_location": "高雄市",
        "station_name": "高雄",
        "lat": 22.56,
        "lon": 120.30,
    },
    "高雄港第一航道": {
        "depth": 15.0,
        "cwa_location": "高雄市",
        "station_name": "高雄",
        "lat": 22.61,
        "lon": 120.27,
    },
    "基隆港主航道": {
        "depth": 15.5,
        "cwa_location": "基隆市",
        "station_name": "基隆",
        "lat": 25.15,
        "lon": 121.75,
    },
    "臺中港外航道": {
        "depth": 16.0,
        "cwa_location": "臺中市",
        "station_name": "臺中港",
        "lat": 24.26,
        "lon": 120.51,
    },
    "臺北港進港航道": {
        "depth": 16.0,
        "cwa_location": "新北市",
        "station_name": "臺北港",
        "lat": 25.16,
        "lon": 121.37,
    },
    "淡水港航道": {
        "depth": 9.0,
        "cwa_location": "新北市",
        "station_name": "淡水",
        "lat": 25.17,
        "lon": 121.43,
    },
    "花蓮港進港航道": {
        "depth": 14.0,
        "cwa_location": "花蓮縣",
        "station_name": "花蓮",
        "lat": 23.98,
        "lon": 121.63,
    },
    "蘇澳港進港航道": {
        "depth": 15.0,
        "cwa_location": "宜蘭縣",
        "station_name": "蘇澳",
        "lat": 24.60,
        "lon": 121.87,
    },
    "安平港進港航道": {
        "depth": 12.0,
        "cwa_location": "臺南市",
        "station_name": "安平",
        "lat": 22.98,
        "lon": 120.15,
    },
    "麥寮工業港": {
        "depth": 24.0,
        "cwa_location": "雲林縣",
        "station_name": "麥寮",
        "lat": 23.78,
        "lon": 120.14,
    },
}

# --- 2. GPS 定位與港口選擇 ---
st.subheader("📍 港口與航道選擇")
geo_data = get_geolocation()
auto_detected_port = "高雄港第二航道"

if geo_data and "coords" in geo_data:
    user_lat = geo_data["coords"]["latitude"]
    user_lon = geo_data["coords"]["longitude"]
    min_dist = float("inf")
    for port_name, info in TAIWAN_PORTS.items():
        dist = (user_lat - info["lat"]) ** 2 + (user_lon - info["lon"]) ** 2
        if dist < min_dist:
            min_dist = dist
            auto_detected_port = port_name
    st.success(f"📍 自動定位至最近港口：**{auto_detected_port}**")

port_options = list(TAIWAN_PORTS.keys())
default_index = port_options.index(auto_detected_port)
selected_port = st.selectbox(
    "請選擇目標港口/航道：", port_options, index=default_index
)

current_port_info = TAIWAN_PORTS[selected_port]
channel_depth = current_port_info["depth"]
cwa_location = current_port_info["cwa_location"]
station_name = current_port_info["station_name"]

# --- 3. 船舶吃水與動態 Squat (下沉量) 計算 ---
st.subheader("🚢 船舶參數與動態 Squat 下沉量計算")
col1, col2, col3 = st.columns(3)
with col1:
    draft = st.number_input(
        "靜態吃水 Static Draft (m)",
        min_value=5.0,
        max_value=25.0,
        value=16.0,
        step=0.1,
    )
with col2:
    speed = st.number_input(
        "對地航速 Speed (kts)",
        min_value=0.0,
        max_value=25.0,
        value=6.0,
        step=0.5,
    )
with col3:
    cb = st.number_input(
        "方形係數 Block Coeff (Cb)",
        min_value=0.50,
        max_value=0.95,
        value=0.80,
        step=0.05,
    )

squat = round((cb * (speed**2)) / 100.0, 2)
dynamic_draft = round(draft + squat, 2)

st.write(
    f"**航道設計水深**：`{channel_depth}m` ｜ **計算下沉量 (Squat)**：`{squat}m` ｜ **總動態吃水**：`{dynamic_draft}m`"
)
# --- 4. 完全呼叫中央氣象署 (CWA) API 抓取資料 ---
CWA_API_KEY = "CWA-BD9BB68F-C6F0-4960-B0F0-98E82A8C3AB3"


@st.cache_data(ttl=1800)  # 快取 30 分鐘
def fetch_cwa_api_tides(api_key, target_station, target_city):
    """從中央氣象署 F-A0021-001 API 抓取並匹配潮汐預報數據"""
    url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0021-001"
    # 不傳 LocationName 參數，直接抓取全台資料後在本地匹配，避免名稱不符合問題
    params = {"Authorization": api_key}
    try:
        res = requests.get(
            url, params=params, timeout=10, verify=False
        )
        if res.status_code == 200:
            data = res.json()
            records = data.get("records", {})

            locations = (
                records.get("location")
                or records.get("Station")
                or records.get("SeaLocation")
                or []
            )

            if isinstance(locations, dict):
                locations = [locations]

            parsed_tides = {}

            # 遍歷所有氣象署測站尋找匹配項目
            for loc in locations:
                loc_name = str(
                    loc.get("locationName") or loc.get("StationName") or ""
                )

                # 比對測站名稱或縣市名稱 (例如 "高雄" 或 "高雄市")
                if target_station in loc_name or target_city in loc_name:
                    valid_times = (
                        loc.get("validTime")
                        or loc.get("validtime")
                        or loc.get("WeatherElement", [])
                    )
                    for item in valid_times:
                        t_str = (
                            item.get("startTime") or item.get("DataTime") or ""
                        )
                        elements = (
                            item.get("weatherElement")
                            or item.get("Element")
                            or []
                        )
                        for elem in elements:
                            elem_name = elem.get("elementName") or elem.get(
                                "ElementName"
                            )
                            if elem_name == "TideHeights":
                                cm_val = float(
                                    elem.get("elementValue")
                                    or elem.get("ElementValue")
                                )
                                parsed_tides[t_str] = round(
                                    cm_val / 100.0, 2
                                )

                    if parsed_tides:
                        return parsed_tides, None

            return (
                None,
                f"未找到【{target_station} / {target_city}】之潮汐測站資料",
            )
        else:
            return None, f"HTTP 錯誤代碼: {res.status_code}"
    except Exception as e:
        return None, f"連線解析異常: {str(e)}"


# 執行 API 抓取 (同時傳入測站名與縣市名進行雙重比對)
cwa_tides, err_msg = fetch_cwa_api_tides(
    CWA_API_KEY, station_name, cwa_location
)
