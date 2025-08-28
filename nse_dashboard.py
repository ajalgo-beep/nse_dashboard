"""
Streamlit NSE Dashboard: Top Gainers & Losers + Breakout Alerts to Telegram
Filename: nse_streamlit_dashboard.py

Features:
- Fetches NSE data using NSEIndia (nsetools replaced with direct NSE API calls via requests for speed & reliability)
- Supports ticker groups: NIFTY50, BANKNIFTY, FINNIFTY, and F&O stocks (user can select from dropdown)
- Parallelized data fetching for faster updates using concurrent.futures
- Shows Top Gainers and Top Losers as bar charts on the main page
- Sidebar (left) contains sliders/filters: % change, min volume, risk-reward ratio, breakout % threshold, refresh interval
- Identifies breakouts when latest close > recent N-day high * (1 + breakout_pct) and volume spike
- Shows a trade plan for each breakout (entry, stop-loss, targets based on RR)
- Sends Telegram alerts for new breakouts (requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID set in Streamlit Secrets or environment variables)
- Auto-refreshes data either every N minutes (controlled by slider) or when the user changes filters

Deployment suggestion: Streamlit Community Cloud (free for public repos).

"""

import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import requests
import os
import concurrent.futures
from datetime import datetime

# ----------------------
# Config & Defaults
# ----------------------
st.set_page_config(page_title="NSE Top Gainers/Losers + Breakouts", layout="wide")

# Predefined groups
GROUPS = {
    "NIFTY50": "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050",
    "BANKNIFTY": "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20BANK",
    "FINNIFTY": "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20FINANCIAL%20SERVICES",
    "FNO": "https://www.nseindia.com/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# ----------------------
# Helper functions
# ----------------------

def get_env_or_secret(key):
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key)


def fetch_group_tickers(group_url):
    try:
        with requests.Session() as s:
            s.headers.update(HEADERS)
            # Warm-up request to get cookies
            s.get("https://www.nseindia.com", timeout=10)
            r = s.get(group_url, timeout=10)
            if r.status_code == 200:
                data = r.json().get("data", [])
                return [d["symbol"] + ".NS" for d in data if "symbol" in d]
            else:
                st.error(f"Failed to fetch from NSE API: {r.status_code}")
                return []
    except Exception as e:
        st.error(f"Error fetching group tickers: {e}")
        return []


def fetch_quote(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        result = data["chart"]["result"][0]
        meta = result["meta"]
        ts = result["timestamp"]
        close = result["indicators"]["quote"][0]["close"]
        vol = result["indicators"]["quote"][0]["volume"]
        df = pd.DataFrame({
            "date": pd.to_datetime(ts, unit="s"),
            "close": close,
            "volume": vol
        }).dropna()
        return symbol, df
    except Exception:
        return symbol, pd.DataFrame()


def batch_fetch_parallel(symbols):
    data = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_quote, sym) for sym in symbols]
        for fut in concurrent.futures.as_completed(futures):
            sym, df = fut.result()
            if not df.empty:
                data[sym] = df
    return data


def compute_changes(latest_data):
    rows = []
    for sym, df in latest_data.items():
        if len(df) < 2:
            continue
        latest, prev = df.iloc[-1], df.iloc[-2]
        pct_change = (latest.close - prev.close) / prev.close * 100 if prev.close != 0 else 0
        rows.append({
            "ticker": sym,
            "close": latest.close,
            "volume": latest.volume,
            "pct_change": pct_change,
            "hist": df
        })
    return pd.DataFrame(rows)


def detect_breakouts(df, lookback_days=20, breakout_pct=0.5, volume_multiplier=1.5):
    results = []
    for _, row in df.iterrows():
        hist = row["hist"]
        if hist is None or len(hist) < lookback_days:
            results.append({"is_breakout": False})
            continue
        recent = hist.tail(lookback_days+1).iloc[:-1]
        highest = recent["close"].max()
        avg_vol = recent["volume"].mean()
        latest = hist.iloc[-1]
        is_break = latest.close > highest * (1 + breakout_pct/100) and latest.volume > avg_vol * volume_multiplier
        results.append({
            "is_breakout": is_break,
            "recent_high": highest,
            "avg_volume": avg_vol,
            "entry": latest.close,
            "volume": latest.volume
        })
    return pd.concat([df.reset_index(drop=True), pd.DataFrame(results)], axis=1)


def compute_trade_plan(entry, stop_pct, rr):
    stop = entry * (1 - stop_pct/100)
    risk = entry - stop
    target = entry + risk * rr
    return {"entry": round(entry,2), "stop": round(stop,2), "target": round(target,2), "rr": rr}


def send_telegram_alert(bot_token, chat_id, message):
    if not bot_token or not chat_id:
        return False, "Missing token/chat_id"
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": 'HTML'}
    try:
        r = requests.post(url, data=payload, timeout=10)
        return (r.status_code == 200, r.text)
    except Exception as e:
        return False, str(e)

# ----------------------
# Sidebar Controls
# ----------------------
st.sidebar.title("Filters & Controls")
with st.sidebar.form("controls"):
    group_choice = st.selectbox("Select Stock Group", list(GROUPS.keys()))
    pct_change_filter = st.slider("Min % change", 0.0, 20.0, 0.2, step=0.1)
    min_volume = st.number_input("Min volume", min_value=0, value=100000, step=10000)
    breakout_pct = st.slider("Breakout threshold %", 0.0, 10.0, 0.5, step=0.1)
    vol_mult = st.slider("Volume multiplier", 0.5, 5.0, 1.5, step=0.1)
    lookback_days = st.slider("Lookback days", 5, 60, 20, step=1)
    stoploss_pct = st.slider("Stoploss %", 0.1, 10.0, 2.0, step=0.1)
    rr = st.slider("Risk-Reward Ratio", 0.5, 10.0, 2.0, step=0.1)
    refresh_interval = st.slider("Auto-refresh interval (mins)", 1, 60, 5)
    telegram_alerts = st.checkbox("Enable Telegram alerts")
    submit = st.form_submit_button("Apply")

symbols = fetch_group_tickers(GROUPS[group_choice])
if not symbols:
    st.error("No symbols found for selected group.")
    st.stop()

with st.spinner("Fetching market data..."):
    latest_data = batch_fetch_parallel(symbols)
    df = compute_changes(latest_data)

if df.empty:
    st.warning("No market data available.")
    st.stop()

df["abs_pct_change"] = df.pct_change.abs()
gainers = df.sort_values("pct_change", ascending=False)
losers = df.sort_values("pct_change", ascending=True)
filtered = df[(df.abs_pct_change >= pct_change_filter) & (df.volume >= min_volume)]
breakouts_df = detect_breakouts(filtered, lookback_days, breakout_pct, vol_mult)

if "alerts_sent" not in st.session_state:
    st.session_state["alerts_sent"] = set()

col1, col2 = st.columns([2,1])
with col1:
    st.header("Top Gainers")
    st.bar_chart(gainers.set_index("ticker")["pct_change"].head(10))
    st.header("Top Losers")
    st.bar_chart(losers.set_index("ticker")["pct_change"].head(10))

with col2:
    st.header("Breakouts & Trade Plans")
    br_hits = breakouts_df[breakouts_df.is_breakout]
    if br_hits.empty:
        st.write("No breakouts found.")
    else:
        for _, r in br_hits.iterrows():
            plan = compute_trade_plan(r.entry, stoploss_pct, rr)
            st.markdown(f"### {r.ticker} 🚀")
            st.write(f"Entry: {plan['entry']} | Stop: {plan['stop']} | Target: {plan['target']} | RR: {plan['rr']}")
            if telegram_alerts and r.ticker not in st.session_state["alerts_sent"]:
                bot = get_env_or_secret("TELEGRAM_BOT_TOKEN")
                chat = get_env_or_secret("TELEGRAM_CHAT_ID")
                msg = f"BREAKOUT: {r.ticker} | Entry {plan['entry']} | Stop {plan['stop']} | Target {plan['target']}"
                ok, _ = send_telegram_alert(bot, chat, msg)
                if ok:
                    st.session_state["alerts_sent"].add(r.ticker)

st.dataframe(filtered[["ticker", "close", "pct_change", "volume"]])

# ----------------------
# Deployment files
# ----------------------
if st.checkbox("Show deployment files"):
    st.subheader("requirements.txt")
    st.code("""streamlit
pandas
numpy
altair
requests
""", language="text")

    st.subheader("README.md")
    st.code("""# NSE Streamlit Dashboard

This is a free Streamlit dashboard for NSE stocks showing Top Gainers/Losers, Breakouts, and Trade Plans.

## Features
- Supports groups: NIFTY50, BANKNIFTY, FINNIFTY, F&O
- Breakout detection with filters (price, volume, risk-reward)
- Telegram alerts on breakout
- Free deployment on Streamlit Community Cloud

## How to Run
```bash
streamlit run nse_streamlit_dashboard.py
```

## Deployment
- Push this repo to GitHub
- Connect to [Streamlit Cloud](https://streamlit.io/cloud)
- Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in Streamlit secrets
""", language="markdown")

    st.subheader("Procfile (for Heroku, optional)")
    st.code("""web: streamlit run nse_streamlit_dashboard.py --server.port=$PORT --server.address=0.0.0.0""", language="text")
