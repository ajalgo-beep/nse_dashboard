import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import time
from datetime import datetime

# NSE headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/118.0.0.0 Safari/537.36"
}

def get_nse_gainers_losers():
    """Fetch Top Gainers & Losers from NSE (NIFTY 50)"""
    try:
        url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050"
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=HEADERS, timeout=10)  # preload cookies
        response = session.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()["data"]

        df = pd.DataFrame(data)
        df["pChange"] = df["pChange"].astype(float)

        gainers = df.sort_values("pChange", ascending=False).head(10)
        losers = df.sort_values("pChange", ascending=True).head(10)

        return gainers, losers
    except Exception as e:
        st.error(f"⚠️ Error fetching NSE data: {e}")
        return pd.DataFrame(), pd.DataFrame()

def generate_trade_plan(df, direction="long", rr_ratio=2):
    """Generate trade plan with Risk:Reward levels"""
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
            "entry": round(entry,2),
            "stoploss": round(stop,2),
            "target": round(target,2),
            "risk_reward": rr_ratio
        })
    return pd.DataFrame(plans)

# Streamlit UI
st.set_page_config(page_title="📈 NSE Screener", layout="wide")
st.title("📊 NSE NIFTY 50 Gainers, Losers & Trade Plans")

min_change = st.sidebar.slider("📊 Min % Change", 0, 10, 2, 1)
rr_ratio = st.sidebar.slider("🎯 Risk:Reward Ratio", 1, 4, 2, 1)
refresh_time = st.sidebar.slider("⏱ Auto Refresh (mins)", 1, 30, 5, 1)

st.info(f"⚡ Screener refreshes every {refresh_time} mins")

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
st.write(f"⏰ Last Updated: {now}")

# ✅ Always show Top 10 Gainers and Losers
gainers_df, losers_df = get_nse_gainers_losers()

col1, col2 = st.columns(2)

with col1:
    st.subheader("🔥 Top 10 Gainers (NIFTY 50)")
    if not gainers_df.empty:
        st.dataframe(gainers_df[["symbol", "lastPrice", "pChange", "dayHigh", "dayLow", "totalTradedValue"]])
        fig_g = px.bar(gainers_df, x="symbol", y="pChange",
                       title="Top Gainers % Change", color="pChange", color_continuous_scale="Greens")
        st.plotly_chart(fig_g, use_container_width=True)

with col2:
    st.subheader("💀 Top 10 Losers (NIFTY 50)")
    if not losers_df.empty:
        st.dataframe(losers_df[["symbol", "lastPrice", "pChange", "dayHigh", "dayLow", "totalTradedValue"]])
        fig_l = px.bar(losers_df, x="symbol", y="pChange",
                       title="Top Losers % Change", color="pChange", color_continuous_scale="Reds")
        st.plotly_chart(fig_l, use_container_width=True)

# 📊 Breakout Trade Plans
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
        trade_plans_sh
