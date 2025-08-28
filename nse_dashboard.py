import streamlit as st
import pandas as pd
import time
import plotly.express as px
from datetime import datetime
from nsetools import Nse

# Initialize NSE API
nse = Nse()

# Trade Plan Generator
def generate_trade_plan(df, direction="long", rr_ratio=2):
    plans = []
    for _, row in df.iterrows():
        entry = row["ltp"]
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

try:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ✅ Get gainers & losers from nsetools
    gainers = nse.get_top_gainers()
    losers = nse.get_top_losers()

    # Convert to DataFrame
    gainers_df = pd.DataFrame(gainers)
    losers_df = pd.DataFrame(losers)

    st.write(f"⏰ Last Updated: {now}")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔥 Top Gainers")
        st.dataframe(gainers_df[["symbol", "ltp", "netPrice", "highPrice", "lowPrice"]])
        fig_g = px.bar(gainers_df.head(10), x="symbol", y="netPrice",
                   title="Top Gainers % Change", color="netPrice", color_continuous_scale="Greens")
        st.plotly_chart(fig_g, use_container_width=True)

    with col2:
        st.subheader("💀 Top Losers")
        st.dataframe(losers_df[["symbol", "ltp", "netPrice", "highPrice", "lowPrice"]])
        fig_l = px.bar(losers_df.head(10), x="symbol", y="netPrice",
                   title="Top Losers % Change", color="netPrice", color_continuous_scale="Reds")
        st.plotly_chart(fig_l, use_container_width=True)


    # Breakout Plans
    st.markdown("---")
    st.subheader("📊 Breakout Trade Plans")

    gf = gainers_df[gainers_df["netPrice"] >= min_change]
    lf = losers_df[losers_df["netPrice"] <= -min_change]

    col3, col4 = st.columns(2)

    with col3:
        st.subheader("📈 Bullish Breakouts")
        trade_plans_long = generate_trade_plan(gf, "long", rr_ratio)
        st.dataframe(trade_plans_long)

    with col4:
        st.subheader("📉 Bearish Breakdowns")
        trade_plans_short = generate_trade_plan(lf, "short", rr_ratio)
        st.dataframe(trade_plans_short)

    time.sleep(refresh_time * 60)
    st.experimental_rerun()

except Exception as e:
    st.error(f"⚠️ Error fetching NSE data: {e}")
