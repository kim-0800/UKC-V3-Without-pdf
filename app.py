from datetime import datetime, timedelta
import pandas as pd
import pytz
import requests
import streamlit as st
from streamlit_js_eval import get_geolocation

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
def fetch_cwa_api_tides(api_key, location):
    """直接從中央氣象署 F-A0021-001 開放資料 API 抓取逐時潮汐預報數據"""
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0021-001?Authorization={api_key}&LocationName={location}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            locations = data["records"]["location"]
            parsed_tides = {}
            for loc in locations:
                if loc.get("locationName") == location:
                    station_data = loc.get("validTime", [])
                    for item in station_data:
                        t_str = item["startTime"]
                        element_val = item.get("weatherElement", [])
                        for elem in element_val:
                            if elem["elementName"] == "TideHeights":
                                cm_val = float(elem["elementValue"])
                                parsed_tides[t_str] = round(
                                    cm_val / 100.0, 2
                                )  # cm 轉成公尺 m
                    if parsed_tides:
                        return parsed_tides, None
            return None, "API 回傳資料中無此測站數據"
        else:
            return None, f"HTTP 錯誤代碼: {res.status_code}"
    except Exception as e:
        return None, f"連線異常: {str(e)}"


# 執行 API 抓取
cwa_tides, err_msg = fetch_cwa_api_tides(CWA_API_KEY, cwa_location)

# --- 5. 處理未來的 24 小時預報列表 ---
processed_results = []
current_status = None
current_ukc_pct = 0.0

if cwa_tides:
    st.toast(
        f"✅ 成功從中央氣象署抓取【{cwa_location}-{station_name}】最新潮汐預報！"
    )

    base_time = now.replace(minute=0, second=0, microsecond=0)

    for i in range(24):
        t_time = base_time + timedelta(hours=i)
        time_key = t_time.strftime("%Y-%m-%d %H:00:00")

        # 若 API 有該時間點則讀取，若無則標示為 None
        tide = cwa_tides.get(time_key, None)

        if tide is not None:
            avail_depth = channel_depth + tide
            ukc = avail_depth - dynamic_draft
            ukc_pct = (ukc / dynamic_draft) * 100

            if ukc_pct >= 15.0:
                status_code = "GREEN"
                status = "🟢 安全通行"
            elif ukc_pct >= 10.0:
                status_code = "YELLOW"
                status = "🟡 限制通行"
            else:
                status_code = "RED"
                status = "🔴 禁止過灘"

            if i == 0:
                current_status = status_code
                current_ukc_pct = ukc_pct

            processed_results.append(
                {
                    "datetime": t_time,
                    "時間": t_time.strftime("%H:00")
                    + (" (現在)" if i == 0 else ""),
                    "time_clean": t_time.strftime("%H:00"),
                    "潮高(m)": tide,
                    "可用水深(m)": round(avail_depth, 2),
                    "UKC %": round(ukc_pct, 1),
                    "狀態": status,
                    "status_code": status_code,
                }
            )

# --- 6. 畫面顯示邏輯 ---
if not cwa_tides or not processed_results:
    st.error(f"❌ 潮汐資料抓取失敗或氣象署 API 無回應。原因：{err_msg}")
    st.info("💡 請確認網路連線正常，或稍後再試。")
else:
    # 根據動態動態狀態改變背景色彩
    bg_color_map = {"GREEN": "#e8f8f5", "YELLOW": "#fef9e7", "RED": "#fadbd8"}
    bg_color = bg_color_map.get(current_status, "#ffffff")

    st.markdown(
        f"""
        <style>
        .stApp {{
            background-color: {bg_color};
            transition: background-color 0.5s ease;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # 當前過灘狀態
    st.subheader("⏱️ 當前過灘狀態與潮窗推算")
    if current_status == "GREEN":
        st.success(
            f"🟢 **【{selected_port}】當前時刻 ({now.strftime('%H:%M')}) 可安全過灘入港！** (UKC 裕度: `{current_ukc_pct:.1f}%`)"
        )
    elif current_status == "YELLOW":
        st.warning(
            f"🟡 **【{selected_port}】當前時刻 ({now.strftime('%H:%M')}) 為限制通行狀況。** (UKC 裕度: `{current_ukc_pct:.1f}%`)"
        )
    else:
        st.error(
            f"🔴 **【{selected_port}】當前時刻 ({now.strftime('%H:%M')}) 禁止過灘！** 水深裕度不足 (UKC 裕度: `{current_ukc_pct:.1f}%`)"
        )

    st.markdown("---")

    # 圖表與表格
    st.subheader("📈 未來 24 小時潮圖與水深裕度分析")
    df_chart = pd.DataFrame(processed_results)
    chart_data = pd.DataFrame(
        {
            "時間": df_chart["time_clean"],
            "可用總水深 (m)": df_chart["可用水深(m)"],
            "動態吃水 (m)": [dynamic_draft] * len(df_chart),
        }
    ).set_index("時間")

    st.line_chart(chart_data)

    st.subheader("📊 未來 24 小時動態數據細節")
    df_display = pd.DataFrame(processed_results)[
        ["時間", "潮高(m)", "可用水深(m)", "UKC %", "狀態"]
    ]
    st.dataframe(df_display, use_container_width=True)