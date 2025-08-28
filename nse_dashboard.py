import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import time
from datetime import datetime

# NSE headers (acts like a browser request)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/118.0.0.0 Safari/537.36"
}

def get_nse_data(type_="gainers"):
    """Fetch NSE Top Gainers/Losers from official API"""
    try:
        url = f"https://www.nseindia.com/api/live-analysis-variations?index=equities&type={type_}"
        session = requests.Session()
        # preload cookies
        session.get("https://www.nseindia.com", headers=HEADERS, timeout=10)
        response = session.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()["data"]
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"⚠️ Error fetching {type_}: {e}")
        return pd.DataFrame()

def generate_trade_plan(df, direction="long", rr_ratio=2):
    """Generate trade plan with R:R levels"""
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

min_change = st.sidebar.slider("📊 Min % Change", 0, 10, 2, 1)
rr_ratio = st.sidebar.slider("🎯 Risk:Reward Ratio", 1, 4, 2, 1)
refresh_time = st.sidebar.slider("⏱ Auto Refresh (mins)", 1, 30, 5, 1)

st.info(f"⚡ Screener refreshes every {refresh_time} mins")

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
st.write(f"⏰ Last Updated: {now}")

# ✅ Always show Top Gainers and Losers
gainers_df = get_nse_data("gainers")
losers_df = get_nse_data("losers")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🔥 Top Gainers")
    if not gainers_df.empty:
        st.dataframe(gainers_df[["symbol", "lastPrice", "pChange", "dayHigh", "dayLow"]])
        fig_g = px.bar(gainers_df.head(10), x="symbol", y="pChange",
                       title="Top Gainers % Change", color="pChange", color_continuous_scale="Greens")
        st.plotly_chart(fig_g, use_container_width=True)

with col2:
    st.subheader("💀 Top Losers")
    if not losers_df.empty:
        st.dataframe(losers_df[["symbol", "lastPrice", "pChange", "dayHigh", "dayLow"]])
        fig_l = px.bar(losers_df.head(10), x="symbol", y="pChange",
                       title="Top Losers % Change", color="pChange", color_continuous_scale="Reds")
        st.plotly_chart(fig_l, use_container_width=True)

# 📊 Breakout Plans
st.markdown("---")
st.subheader("📊 Breakout Trade Plans")

gf = gainers_df[gainers_df["pChange"] >= min_change] if not gainers_df.empty else pd.DataFrame()
lf = losers_df[losers_df["pChange"] <= -min_change] if not losers_df.empty else pd.DataFrame()

col3, col4 = st.columns(2)

with col3:
    st.subheader("📈 Bullish Breakouts")
    if not gf.empty:
        trade_plans_long = generate_trade_plan(gf, "long", rr_ratio)
        st.dataframe(trade_plans_long)

with col4:
    st.subheader("📉 Bearish Breakdowns")
    if not lf.empty:
        trade_plans_short = generate_trade_plan(lf, "short", rr_ratio)
        st.dataframe(trade_plans_short)

# Auto-refresh
time.sleep(refresh_time * 60)
st.experimental_rerun()
