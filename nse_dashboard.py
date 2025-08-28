import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import plotly.express as px
import requests as req
import time

# ===================
# NSE CONFIG
# ===================
SEGMENTS = {
    "NIFTY 50": "nifty",
    "NIFTY Next 50": "juniorNifty",
    "NIFTY Midcap 50": "niftyMidcap50",
    "NIFTY Bank": "niftyBank",
    "F&O Securities": "securities",
}

BASE_URL = "https://www.nseindia.com/api/live-analysis-variations?index={}&type={}"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br"
}

# ===================
# TELEGRAM CONFIG
# ===================
TELEGRAM_ENABLED = True
TELEGRAM_BOT_TOKEN = "your_bot_token"      # 🔑 Replace with BotFather token
TELEGRAM_CHAT_ID = "your_chat_id"          # 🔑 Replace with your chat id

# ===================
# FUNCTIONS
# ===================
def get_nse_data(segment, type_="gainers"):
    try:
        session = requests.Session()
        # First request to set cookies
        session.get("https://www.nseindia.com", headers=HEADERS, timeout=10)

        url = f"https://www.nseindia.com/api/live-analysis-variations?index={segment}&type={type_}"
        response = session.get(url, headers=HEADERS, timeout=10)

        # Sometimes NSE returns blank → handle safely
        if response.status_code != 200 or response.text.strip() == "":
            return pd.DataFrame()

        data = response.json().get('data', [])
        return pd.DataFrame(data)

    except Exception as e:
        print(f"⚠️ Error in get_nse_data: {e}")
        return pd.DataFrame()

def generate_trade_plan(df, direction="long", rr_ratio=2):
    trade_plans = []
    for _, row in df.iterrows():
        entry = row['lastPrice']
        if direction == "long":
            stoploss = row['dayLow']
            risk = entry - stoploss
            target = entry + (risk * rr_ratio)
        else:
            stoploss = row['dayHigh']
            risk = stoploss - entry
            target = entry - (risk * rr_ratio)

        if risk > 0:
            rr = (abs(target - entry)) / risk
            trade_plans.append({
                "symbol": row['symbol'],
                "entry": round(entry, 2),
                "stoploss": round(stoploss, 2),
                "target": round(target, 2),
                "RRR": round(rr, 2),
                "pChange": round(row['pChange'], 2),
                "volume": row.get('totalTradedVolume', 'NA')
            })
    return pd.DataFrame(trade_plans)

def send_telegram_alert(message):
    if not TELEGRAM_ENABLED:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        req.post(url, data=payload)
    except Exception as e:
        st.error(f"⚠️ Telegram Error: {e}")

def push_alerts(trades, direction):
    for _, row in trades.iterrows():
        msg = (f"📢 Breakout Alert ({direction.upper()})\n"
               f"Symbol: {row['symbol']}\n"
               f"Entry: {row['entry']}\n"
               f"SL: {row['stoploss']}\n"
               f"TGT: {row['target']}\n"
               f"RRR: {row['RRR']}\n"
               f"% Change: {row['pChange']}%\n"
               f"Vol: {row['volume']}")
        send_telegram_alert(msg)

# ===================
# STREAMLIT UI
# ===================
st.set_page_config(page_title="📈 NSE Breakout Screener + Telegram Alerts", layout="wide")
st.title("📊 NSE Breakout Screener + Trade Plan + Auto Telegram Alerts")

segment_name = st.sidebar.selectbox("📌 Select Market Segment", list(SEGMENTS.keys()))
segment = SEGMENTS[segment_name]

min_change = st.sidebar.slider("📊 Min % Change", min_value=0, max_value=10, value=2, step=1)
min_volume = st.sidebar.number_input("📊 Min Volume", min_value=0, value=100000)
rr_ratio = st.sidebar.slider("🎯 Risk:Reward Ratio", min_value=1, max_value=4, value=2, step=1)
refresh_time = st.sidebar.slider("⏱ Auto Refresh (mins)", min_value=1, max_value=30, value=5, step=1)

st.info(f"⚡ Screener will auto-refresh every {refresh_time} minutes and push alerts to Telegram")

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

        # Apply filters
        if 'totalTradedVolume' in gainers_df.columns:
            gainers_df = gainers_df[(gainers_df['pChange'] >= min_change) & (gainers_df['totalTradedVolume'] >= min_volume)]
            losers_df = losers_df[(losers_df['pChange'] <= -min_change) & (losers_df['totalTradedVolume'] >= min_volume)]
        else:
            gainers_df = gainers_df[(gainers_df['pChange'] >= min_change)]
            losers_df = losers_df[(losers_df['pChange'] <= -min_change)]

        st.write(f"⏰ Last Updated: {now}")

        col1, col2 = st.columns(2)

        # ---- Bullish ----
        with col1:
            st.subheader("📈 Bullish Breakout Plans")
            trade_plans_long = generate_trade_plan(gainers_df, direction="long", rr_ratio=rr_ratio)
            st.dataframe(trade_plans_long)
            if not trade_plans_long.empty:
                push_alerts(trade_plans_long, "long")

        # ---- Bearish ----
        with col2:
            st.subheader("📉 Bearish Breakdown Plans")
            trade_plans_short = generate_trade_plan(losers_df, direction="short", rr_ratio=rr_ratio)
            st.dataframe(trade_plans_short)
            if not trade_plans_short.empty:
                push_alerts(trade_plans_short, "short")

    else:
        st.warning("⚠️ No breakout data available right now.")

    # Auto-refresh
    time.sleep(refresh_time * 60)
    st.experimental_rerun()

except Exception as e:
    st.error(f"⚠️ Error fetching data: {e}")
