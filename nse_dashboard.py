import streamlit as st
import requests
import pandas as pd
import time
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime

# NSE Headers
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br"
}

# NSE API fetch
def get_nse_data(segment, type_="gainers"):
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=HEADERS, timeout=10)
        url = f"https://www.nseindia.com/api/live-analysis-variations?index={segment}&type={type_}"
        response = session.get(url, headers=HEADERS, timeout=10)

        if response.status_code != 200 or response.text.strip() == "":
            return pd.DataFrame()

        data = response.json().get('data', [])
        return pd.DataFrame(data)
    except Exception as e:
        print(f"⚠️ Error in get_nse_data: {e}")
        return pd.DataFrame()

# Trade Plan Generator
def generate_trade_plan(df, direction="long", rr_ratio=2):
    plans = []
    for _, row in df.iterrows():
        entry = row['lastPrice']
        if direction == "long":
            stop = row['dayLow']
            target = entry + (entry - stop) * rr_ratio
        else:
            stop = row['dayHigh']
            target = entry - (stop - entry) * rr_ratio

        plans.append({
            "symbol": row['symbol'],
            "entry": entry,
            "stoploss": stop,
            "target": target,
            "risk_reward": rr_ratio
        })
    return pd.DataFrame(plans)

# Streamlit UI
st.set_page_config(page_title="📈 NSE Screener with Charts", layout="wide")
st.title("📊 NSE Gainers, Losers & Breakout Trade Plans")

segment = st.sidebar.selectbox("📌 Select Market Segment", ["SECURITIES IN F&O", "NIFTY 50", "NIFTY NEXT 50"])
min_change = st.sidebar.slider("📊 Min % Change", 0, 10, 2, 1)
rr_ratio = st.sidebar.slider("🎯 Risk:Reward Ratio", 1, 4, 2, 1)
refresh_time = st.sidebar.slider("⏱ Auto Refresh (mins)", 1, 30, 5, 1)

st.info(f"⚡ Screener refreshes every {refresh_time} mins")

try:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    gainers_df = get_nse_data(segment, "gainers")
    losers_df = get_nse_data(segment, "losers")

    if not gainers_df.empty and not losers_df.empty:
        keep_cols = ['symbol', 'lastPrice', 'pChange', 'dayHigh', 'dayLow', 'openPrice', 'previousClose']
        if 'totalTradedVolume' in gainers_df.columns:
            keep_cols.append('totalTradedVolume')

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

        gf = gainers_df[gainers_df['pChange'] >= min_change]
        lf = losers_df[losers_df['pChange'] <= -min_change]

        col3, col4 = st.columns(2)

        with col3:
            st.subheader("📈 Bullish Breakouts")
            trade_plans_long = generate_trade_plan(gf, "long", rr_ratio)
            st.dataframe(trade_plans_long)

            if not trade_plans_long.empty:
                # Candlestick example for first gainer
                symbol = trade_plans_long.iloc[0]['symbol'] + ".NS"
                data = yf.download(symbol, period="5d", interval="15m")
                fig = go.Figure(data=[go.Candlestick(x=data.index,
                                                     open=data['Open'], high=data['High'],
                                                     low=data['Low'], close=data['Close'])])
                fig.update_layout(title=f"{symbol} Intraday Candlestick", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

        with col4:
            st.subheader("📉 Bearish Breakdowns")
            trade_plans_short = generate_trade_plan(lf, "short", rr_ratio)
            st.dataframe(trade_plans_short)

            if not trade_plans_short.empty:
                symbol = trade_plans_short.iloc[0]['symbol'] + ".NS"
                data = yf.download(symbol, period="5d", interval="15m")
                fig = go.Figure(data=[go.Candlestick(x=data.index,
                                                     open=data['Open'], high=data['High'],
                                                     low=data['Low'], close=data['Close'])])
                fig.update_layout(title=f"{symbol} Intraday Candlestick", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

    else:
        st.warning("⚠️ No data available from NSE right now.")

    time.sleep(refresh_time * 60)
    st.experimental_rerun()

except Exception as e:
    st.error(f"⚠️ Error fetching data: {e}")

