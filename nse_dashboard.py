import streamlit as st
import requests
import pandas as pd
import time
import plotly.express as px
from datetime import datetime

# NSE headers (mandatory for API access)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nseindia.com/",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

# NSE API fetch with session + cookies
def get_nse_data(segment, type_="gainers", debug=True):
    try:
        url = f"https://www.nseindia.com/api/live-analysis-variations?index={segment}&type={type_}"
        session = requests.Session()
        # Get homepage once to load cookies
        session.get("https://www.nseindia.com", headers=HEADERS, timeout=10)  
        response = session.get(url, headers=HEADERS, timeout=10)

        if debug:  # 👀 Print raw text for debugging
            print("------ NSE RAW RESPONSE ------")
            print("Status:", response.status_code)
            print("Headers:", response.headers)
            print("Text (first 500 chars):", response.text[:500])

        if response.status_code != 200 or response.text.strip() == "":
            return pd.DataFrame()

        data = response.json().get("data", [])
        return pd.DataFrame(data)
    except Exception as e:
        print(f"⚠️ Error in get_nse_data: {e}")
        return pd.DataFrame()

# Trade Plan Generator
def generate_trade_plan(df, direction="long", rr_ratio=2):
    plans = []
    for _, row in df.iterrows():
        entry = row["lastPrice"]
        if direction == "long":
            stop = row["dayLow"]
            target = entry + (entry - stop) * rr_ratio
        else:
            stop = row["dayHigh"]
            target = entry - (stop - entry) * rr_ratio

        plans.append({
            "symbol": row["symbol"],
            "entry": entry,
            "stoploss": stop,
            "target": target,
            "risk_reward": rr_ratio
        })
    return pd.DataFrame(plans)

# Streamlit UI
st.set_page_config(page_title="📈 NSE Screener", layout="wide")
st.title("📊 NSE Gainers, Losers & Breakout Trade Plans")

SEGMENTS = {
    "NIFTY 50": "nifty",
    "NIFTY NEXT 50": "nifty_next_50",
    "F&O Securities": "securities_in_fno"
}

segment_name = st.sidebar.selectbox("📌 Select Market Segment", list(SEGMENTS.keys()))
segment = SEGMENTS[segment_name]

min_change = st.sidebar.slider("📊 Min % Change", 0, 10, 2, 1)
rr_ratio = st.sidebar.slider("🎯 Risk:Reward Ratio", 1, 4, 2, 1)
refresh_time = st.sidebar.slider("⏱ Auto Refresh (mins)", 1, 30, 5, 1)

st.info(f"⚡ Screener refreshes every {refresh_time} mins")

try:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    gainers_df = get_nse_data(segment, "gainers")
    losers_df = get_nse_data(segment, "losers")

    if not gainers_df.empty and not losers_df.empty:
        keep_cols = ["symbol", "lastPrice", "pChange", "dayHigh", "dayLow", "openPrice", "previousClose"]
        if "totalTradedVolume" in gainers_df.columns:
            keep_cols.append("totalTradedVolume")

        gainers_df = gainers_df[keep_cols]
        losers_df = losers_df[keep_cols]

        st.write(f"⏰ Last Updated: {now}")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("🔥 Top Gainers")
            st.dataframe(gainers_df)
            fig_g = px.bar(gainers_df.head(10), x="symbol", y="pChange",
                           title="Top Gainers % Change", color="pChange", color_continuous_scale="Greens")
            st.plotly_chart(fig_g, use_container_width=True)

        with col2:
            st.subheader("💀 Top Losers")
            st.dataframe(losers_df)
            fig_l = px.bar(losers_df.head(10), x="symbol", y="pChange",
                           title="Top Losers % Change", color="pChange", color_continuous_scale="Reds")
            st.plotly_chart(fig_l, use_container_width=True)

        # Breakout Plans
        st.markdown("---")
        st.subheader("📊 Breakout Trade Plans")

        gf = gainers_df[gainers_df["pChange"] >= min_change]
        lf = losers_df[losers_df["pChange"] <= -min_change]

        col3, col4 = st.columns(2)

        with col3:
            st.subheader("📈 Bullish Breakouts")
            trade_plans_long = generate_trade_plan(gf, "long", rr_ratio)
            st.dataframe(trade_plans_long)

        with col4:
            st.subheader("📉 Bearish Breakdowns")
            trade_plans_short = generate_trade_plan(lf, "short", rr_ratio)
            st.dataframe(trade_plans_short)

    else:
        st.warning("⚠️ NSE data not available right now. Try again in a few minutes.")

    time.sleep(refresh_time * 60)
    st.experimental_rerun()

except Exception as e:
    st.error(f"⚠️ Error fetching data: {e}")
