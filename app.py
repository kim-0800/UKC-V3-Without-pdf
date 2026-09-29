import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo


# ============================================================
# 基本設定
# ============================================================

st.set_page_config(
    page_title="台灣港口潮汐與 UKC 評估系統",
    page_icon="⚓",
    layout="wide",
)


# ============================================================
# 系統設定
# ============================================================

TW_TZ = ZoneInfo("Asia/Taipei")

CWA_API_URL = (
    "https://opendata.cwa.gov.tw/"
    "api/v1/rest/datastore/F-A0021-001"
)


# ============================================================
# CWA API Key
#
# API Key 不要寫在這裡。
# 請放到 Streamlit Cloud → Settings → Secrets
#
# CWA_API_KEY = "你的 API Key"
# ============================================================

try:
    CWA_API_KEY = st.secrets["CWA_API_KEY"]
except Exception:
    CWA_API_KEY = ""


# ============================================================
# 港口資料
#
# depth = 航道設計水深
# cwa_location = CWA 潮汐地點
#
# 第一版先用固定 CWA 地點。
# 後續可以再進一步改成 stationId 精確對應。
# ============================================================

PORTS = {
    "高雄港第二航道": {
        "depth": 17.0,
        "cwa_location": "高雄",
    },

    "高雄港第一航道": {
        "depth": 15.0,
        "cwa_location": "高雄",
    },

    "基隆港主航道": {
        "depth": 15.5,
        "cwa_location": "基隆",
    },

    "臺中港外航道": {
        "depth": 16.0,
        "cwa_location": "臺中",
    },

    "臺北港進港航道": {
        "depth": 16.0,
        "cwa_location": "臺北",
    },

    "淡水港航道": {
        "depth": 9.0,
        "cwa_location": "淡水",
    },

    "花蓮港進港航道": {
        "depth": 14.0,
        "cwa_location": "花蓮",
    },

    "蘇澳港進港航道": {
        "depth": 15.0,
        "cwa_location": "蘇澳",
    },

    "安平港進港航道": {
        "depth": 12.0,
        "cwa_location": "安平",
    },

    "麥寮工業港": {
        "depth": 24.0,
        "cwa_location": "麥寮",
    },
}


# ============================================================
# 頁面標題
# ============================================================

now = datetime.now(TW_TZ)

st.title("⚓ 台灣港口潮汐與 UKC 評估系統")

st.caption(
    "中央氣象署潮汐資料 × 港口航道水深 × 船舶靜態吃水"
)

st.write(
    f"系統時間：{now.strftime('%Y-%m-%d %H:%M:%S')} "
    "(台灣時間)"
)


# ============================================================
# API Key 檢查
# ============================================================

if not CWA_API_KEY:

    st.error(
        "尚未設定中央氣象署 API Key。"
    )

    st.info(
        """
請到 Streamlit Cloud：

Settings → Secrets

加入：

CWA_API_KEY = "你的 API Key"
"""
    )

    st.stop()


# ============================================================
# 港口選擇
# ============================================================

st.divider()

st.header("📍 1. 選擇港口")

port_name = st.selectbox(
    "目標港口 / 航道",
    list(PORTS.keys()),
)

port_info = PORTS[port_name]

channel_depth = float(
    port_info["depth"]
)

cwa_location = port_info[
    "cwa_location"
]


col1, col2 = st.columns(2)

with col1:

    st.metric(
        "航道設計水深",
        f"{channel_depth:.2f} m",
    )

with col2:

    st.metric(
        "CWA 潮汐地點",
        cwa_location,
    )


# ============================================================
# 船舶吃水
# ============================================================

st.divider()

st.header("🚢 2. 船舶資料")

draft = st.number_input(
    "船舶靜態吃水 (m)",
    min_value=0.1,
    max_value=30.0,
    value=16.0,
    step=0.1,
)


# ============================================================
# CWA API 函式
# ============================================================

@st.cache_data(ttl=1800)
def fetch_cwa_tide(
    api_key: str,
    location_name: str,
):

    params = {
        "Authorization": api_key,
        "locationName": location_name,
        "limit": 1000,
    }

    try:

        response = requests.get(
            CWA_API_URL,
            params=params,
            timeout=20,
        )

    except requests.exceptions.Timeout:

        return None, "CWA API 連線逾時。"

    except requests.exceptions.RequestException as e:

        return None, f"HTTP 連線錯誤：{e}"

    # --------------------------------------------------------
    # HTTP 狀態
    # --------------------------------------------------------

    if response.status_code != 200:

        return None, (
            f"CWA HTTP {response.status_code}\n\n"
            f"{response.text[:500]}"
        )

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    try:

        data = response.json()

    except ValueError:

        return None, (
            "CWA 回傳資料不是有效 JSON。\n\n"
            f"{response.text[:500]}"
        )

    # --------------------------------------------------------
    # API success
    # --------------------------------------------------------

    if str(data.get("success")).lower() != "true":

        return None, (
            "CWA API 回傳失敗。\n\n"
            f"{data}"
        )

    # --------------------------------------------------------
    # records
    # --------------------------------------------------------

    records = data.get(
        "records",
        {}
    )

    locations = records.get(
        "location",
        []
    )

    if not locations:

        return None, (
            f"CWA 沒有回傳 {location_name} "
            "的潮汐地點資料。"
        )

    # --------------------------------------------------------
    # 找地點
    # --------------------------------------------------------

    target_location = None

    for location in locations:

        name = str(
            location.get(
                "locationName",
                ""
            )
        )

        if name == location_name:

            target_location = location
            break

    # --------------------------------------------------------
    # 模糊搜尋
    # --------------------------------------------------------

    if target_location is None:

        for location in locations:

            name = str(
                location.get(
                    "locationName",
                    ""
                )
            )

            if location_name in name:

                target_location = location
                break

    if target_location is None:

        available = [
            location.get(
                "locationName",
                ""
            )
            for location in locations
        ]

        return None, (
            f"找不到 CWA 地點：{location_name}\n\n"
            f"API 回傳地點：{available}"
        )

    # ========================================================
    # 解析潮汐
    # ========================================================

    tide_rows = []

    valid_times = target_location.get(
        "validTime",
        []
    )

    for valid_time in valid_times:

        weather_elements = valid_time.get(
            "weatherElement",
            []
        )

        for element in weather_elements:

            element_name = str(
                element.get(
                    "elementName",
                    ""
                )
            )

            tide_times = element.get(
                "time",
                []
            )

            for tide_time in tide_times:

                data_time = tide_time.get(
                    "dataTime",
                    ""
                )

                if not data_time:
                    continue

                parameters = tide_time.get(
                    "parameter",
                    []
                )

                for parameter in parameters:

                    parameter_name = str(
                        parameter.get(
                            "parameterName",
                            ""
                        )
                    )

                    parameter_value = parameter.get(
                        "parameterValue"
                    )

                    parameter_measure = str(
                        parameter.get(
                            "parameterMeasure",
                            ""
                        )
                    )

                    if parameter_value is None:
                        continue

                    try:

                        value = float(
                            parameter_value
                        )

                    except (
                        ValueError,
                        TypeError
                    ):

                        continue

                    # ------------------------------------------------
                    # 判斷是否為潮高
                    # ------------------------------------------------

                    is_tide = (
                        "潮高" in parameter_name
                        or "Tide" in parameter_name
                        or "height" in parameter_name.lower()
                    )

                    if not is_tide:
                        continue

                    # ------------------------------------------------
                    # 單位
                    # ------------------------------------------------

                    measure_lower = (
                        parameter_measure.lower()
                    )

                    if (
                        "cm" in measure_lower
                        or "公分" in parameter_measure
                    ):

                        value = value / 100.0

                    tide_rows.append(
                        {
                            "datetime": data_time,
                            "tide_m": value,
                            "parameter": parameter_name,
                            "measure": parameter_measure,
                            "station": target_location.get(
                                "locationName",
                                ""
                            ),
                            "station_id": target_location.get(
                                "stationId",
                                ""
                            ),
                        }
                    )

    # ========================================================
    # 沒抓到潮汐
    # ========================================================

    if not tide_rows:

        return None, (
            "API 已成功連線，但沒有解析到潮高資料。"
        )

    # ========================================================
    # DataFrame
    # ========================================================

    df = pd.DataFrame(
        tide_rows
    )

    df = df.drop_duplicates(
        subset=[
            "datetime",
            "tide_m",
        ]
    )

    # --------------------------------------------------------
    # 時間
    # --------------------------------------------------------

    df["datetime"] = pd.to_datetime(
        df["datetime"],
        errors="coerce",
    )

    df = df.dropna(
        subset=["datetime"]
    )

    # --------------------------------------------------------
    # 加上台灣時區
    # --------------------------------------------------------

    if df["datetime"].dt.tz is None:

        df["datetime"] = (
            df["datetime"]
            .dt.tz_localize(
                "Asia/Taipei"
            )
        )

    else:

        df["datetime"] = (
            df["datetime"]
            .dt.tz_convert(
                "Asia/Taipei"
            )
        )

    # --------------------------------------------------------
    # 排序
    # --------------------------------------------------------

    df = df.sort_values(
        "datetime"
    )

    df = df.reset_index(
        drop=True
    )

    return df, None


# ============================================================
# 呼叫 CWA
# ============================================================

st.divider()

st.header("🌊 3. 中央氣象署潮汐資料")

with st.spinner(
    f"正在取得 {cwa_location} 潮汐資料..."
):

    tide_df, error = fetch_cwa_tide(
        CWA_API_KEY,
        cwa_location,
    )


# ============================================================
# API 錯誤
# ============================================================

if error:

    st.error(
        "潮汐資料取得失敗"
    )

    with st.expander(
        "查看詳細錯誤"
    ):

        st.code(
            error
        )

    st.stop()


# ============================================================
# API 成功
# ============================================================

st.success(
    f"✅ CWA API 連線成功 "
    f"｜ 測站：{cwa_location} "
    f"｜ 資料筆數：{len(tide_df)}"
)


# ============================================================
# 找目前時間附近的潮高
# ============================================================

current_time = datetime.now(
    TW_TZ
)

tide_df["time_difference"] = (
    tide_df["datetime"]
    - current_time
).abs()

nearest_index = (
    tide_df["time_difference"]
    .idxmin()
)

nearest = tide_df.loc[
    nearest_index
]

current_tide = float(
    nearest["tide_m"]
)

tide_time = nearest[
    "datetime"
]


# ============================================================
# 目前潮汐
# ============================================================

st.subheader(
    "🕐 目前潮汐"
)

col1, col2, col3 = st.columns(3)

with col1:

    st.metric(
        "目前估算潮高",
        f"{current_tide:.2f} m",
    )

with col2:

    st.metric(
        "對應時間",
        tide_time.strftime(
            "%Y-%m-%d %H:%M"
        ),
    )

with col3:

    difference_minutes = (
        nearest["time_difference"]
        .total_seconds()
        / 60
    )

    st.metric(
        "與目前時間差",
        f"{difference_minutes:.0f} 分鐘",
    )


# ============================================================
# UKC
# ============================================================

st.divider()

st.header("⚓ 4. UKC 評估")


effective_depth = (
    channel_depth
    + current_tide
)

ukc = (
    effective_depth
    - draft
)


col1, col2, col3 = st.columns(3)

with col1:

    st.metric(
        "航道水深",
        f"{channel_depth:.2f} m",
    )

with col2:

    st.metric(
        "目前潮高",
        f"{current_tide:.2f} m",
    )

with col3:

    st.metric(
        "計算水深",
        f"{effective_depth:.2f} m",
    )


st.metric(
    "UKC",
    f"{ukc:.2f} m",
)


# ============================================================
# UKC 結果
#
# 注意：
# 這只是數學上的基本 UKC 計算，
# 尚未加入 Squat、波浪、船舶搖擺、
# 密度、測量誤差、航道安全裕度等因素。
# ============================================================

if ukc < 0:

    st.error(
        f"❌ UKC = {ukc:.2f} m\n\n"
        "以目前輸入條件計算，"
        "船舶靜態吃水超過計算水深。"
    )

elif ukc < 1.0:

    st.warning(
        f"⚠️ UKC = {ukc:.2f} m\n\n"
        "目前剩餘水深裕度較小。"
    )

else:

    st.success(
        f"🟢 UKC = {ukc:.2f} m"
    )


# ============================================================
# 未來潮汐
# ============================================================

st.divider()

st.header("📅 未來潮汐預報")

display_df = tide_df[
    [
        "datetime",
        "tide_m",
    ]
].copy()

display_df["datetime"] = (
    display_df["datetime"]
    .dt.strftime(
        "%Y-%m-%d %H:%M"
    )
)

display_df = display_df.rename(
    columns={
        "datetime": "時間",
        "tide_m": "潮高 (m)",
    }
)

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
)


# ============================================================
# 系統資訊
# ============================================================

with st.expander(
    "🔧 系統 / API 診斷資訊"
):

    st.write(
        "CWA API：",
        CWA_API_URL,
    )

    st.write(
        "CWA 地點：",
        cwa_location,
    )

    st.write(
        "CWA Station ID：",
        nearest.get(
            "station_id",
            "",
        ),
    )

    st.write(
        "資料筆數：",
        len(tide_df),
    )

    st.write(
        "最後更新時間：",
        now.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    )