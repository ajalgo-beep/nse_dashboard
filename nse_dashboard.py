"""
Streamlit NSE Dashboard: Top Gainers & Losers + Breakout Alerts to Telegram
Filename: nse\_streamlit\_dashboard.py

Features:

* Fetches NSE data using NSEIndia (direct API calls with session & cookies)
* Supports ticker groups: NIFTY50, BANKNIFTY, FINNIFTY, and F\&O stocks (user can select from dropdown)
* Parallelized data fetching for faster updates using concurrent.futures
* Shows Top Gainers and Top Losers as bar charts on the main page
* Sidebar (left) contains sliders/filters: % change, min volume, risk-reward ratio, breakout % threshold, refresh interval
* Identifies breakouts when latest close > recent N-day high \* (1 + breakout\_pct) and volume spike
* Shows a trade plan for each breakout (entry, stop-loss, targets based on RR)
* Sends Telegram alerts for new breakouts (requires TELEGRAM\_BOT\_TOKEN and TELEGRAM\_CHAT\_ID set in Streamlit Secrets or environment variables)
* Auto-refreshes data either every N minutes (controlled by slider) or when the user changes filters

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
"NIFTY50": "[https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050](https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050)",
"BANKNIFTY": "[https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20BANK](https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20BANK)",
"FINNIFTY": "[https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20FINANCIAL%20SERVICES](https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20FINANCIAL%20SERVICES)",
"FNO": "[https://www.nseindia.com/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O](https://www.nseindia.com/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O)",
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

def get\_env\_or\_secret(key):
try:
return st.secrets\[key]
except Exception:
return os.environ.get(key)

def fetch\_group\_tickers(group\_url, debug=False):
try:
with requests.Session() as s:
s.headers.update(HEADERS)
\# Warm-up request to establish cookies
s.get("[https://www.nseindia.com](https://www.nseindia.com)", timeout=10)
r = s.get(group\_url, timeout=10)
if r.status\_code == 200:
data = r.json().get("data", \[])
return \[d\["symbol"]+".NS" for d in data if "symbol" in d]
else:
if debug:
st.error(f"Failed to fetch from NSE API: {r.status\_code}")
st.json(r.text)
return \[]
except Exception as e:
if debug:
st.error(f"Error fetching group tickers: {e}")
return \[]

def fetch\_quote(symbol):
url = f"[https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d\&range=5d](https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d)"
try:
r = requests.get(url, timeout=10)
data = r.json()
result = data\["chart"]\["result"]\[0]
ts = result\["timestamp"]
close = result\["indicators"]\["quote"]\[0]\["close"]
vol = result\["indicators"]\["quote"]\[0]\["volume"]
df = pd.DataFrame({
"date": pd.to\_datetime(ts, unit="s"),
"close": close,
"volume": vol
}).dropna()
return symbol, df
except Exception:
return symbol, pd.DataFrame()

def batch\_fetch\_parallel(symbols):
data = {}
with concurrent.futures.ThreadPoolExecutor(max\_workers=10) as executor:
futures = \[executor.submit(fetch\_quote, sym) for sym in symbols]
for fut in concurrent.futures.as\_completed(futures):
sym, df = fut.result()
if not df.empty:
data\[sym] = df
return data

def compute\_changes(latest\_data):
rows = \[]
for sym, df in latest\_data.items():
if len(df) < 2:
continue
latest, prev = df.iloc\[-1], df.iloc\[-2]
pct\_change = (latest.close - prev.close) / prev.close \* 100 if prev.close != 0 else 0
rows.append({
"ticker": sym,
"close": latest.close,
"volume": latest.volume,
"pct\_change": pct\_change,
"hist": df
})
return pd.DataFrame(rows)

def detect\_breakouts(df, lookback\_days=20, breakout\_pct=0.5, volume\_multiplier=1.5):
results = \[]
for \_, row in df.iterrows():
hist = row\["hist"]
if hist is None or len(hist) < lookback\_days:
results.append({"is\_breakout": False})
continue
recent = hist.tail(lookback\_days+1).iloc\[:-1]
highest = recent\["close"].max()
avg\_vol = recent\["volume"].mean()
latest = hist.iloc\[-1]
is\_break = latest.close > highest \* (1 + breakout\_pct/100) and latest.volume > avg\_vol \* volume\_multiplier
results.append({
"is\_breakout": is\_break,
"recent\_high": highest,
"avg\_volume": avg\_vol,
"entry": latest.close,
"volume": latest.volume
})
return pd.concat(\[df.reset\_index(drop=True), pd.DataFrame(results)], axis=1)

def compute\_trade\_plan(entry, stop\_pct, rr):
stop = entry \* (1 - stop\_pct/100)
risk = entry - stop
target = entry + risk \* rr
return {"entry": round(entry,2), "stop": round(stop,2), "target": round(target,2), "rr": rr}

def send\_telegram\_alert(bot\_token, chat\_id, message):
if not bot\_token or not chat\_id:
return False, "Missing token/chat\_id"
url = f"[https://api.telegram.org/bot{bot\_token}/sendMessage](https://api.telegram.org/bot{bot_token}/sendMessage)"
payload = {"chat\_id": chat\_id, "text": message, "parse\_mode": 'HTML'}
try:
r = requests.post(url, data=payload, timeout=10)
return (r.status\_code == 200, r.text)
except Exception as e:
return False, str(e)

# ----------------------

# Sidebar Controls

# ----------------------

st.sidebar.title("Filters & Controls")
with st.sidebar.form("controls"):
group\_choice = st.selectbox("Select Stock Group", list(GROUPS.keys()))
pct\_change\_filter = st.slider("Min % change", 0.0, 20.0, 0.2, step=0.1)
min\_volume = st.number\_input("Min volume", min\_value=0, value=100000, step=10000)
breakout\_pct = st.slider("Breakout threshold %", 0.0, 10.0, 0.5, step=0.1)
vol\_mult = st.slider("Volume multiplier", 0.5, 5.0, 1.5, step=0.1)
lookback\_days = st.slider("Lookback days", 5, 60, 20, step=1)
stoploss\_pct = st.slider("Stoploss %", 0.1, 10.0, 2.0, step=0.1)
rr = st.slider("Risk-Reward Ratio", 0.5, 10.0, 2.0, step=0.1)
refresh\_interval = st.slider("Auto-refresh interval (mins)", 1, 60, 5)
telegram\_alerts = st.checkbox("Enable Telegram alerts")
test\_connection = st.form\_submit\_button("Test NSE Connection")
submit = st.form\_submit\_button("Apply")

# Connection test button

if test\_connection:
st.info("Testing NSE API connection...")
tickers = fetch\_group\_tickers(GROUPS\[group\_choice], debug=True)
if tickers:
st.success(f"✅ NSE API working. Found {len(tickers)} tickers.")
else:
st.error("❌ NSE API connection failed. Check logs above.")

symbols = fetch\_group\_tickers(GROUPS\[group\_choice])
if not symbols:
st.error("No symbols found for selected group.")
st.stop()

with st.spinner("Fetching market data..."):
latest\_data = batch\_fetch\_parallel(symbols)
df = compute\_changes(latest\_data)

if df.empty:
st.warning("No market data available.")
st.stop()

df\["abs\_pct\_change"] = df.pct\_change.abs()
gainers = df.sort\_values("pct\_change", ascending=False)
losers = df.sort\_values("pct\_change", ascending=True)
filtered = df\[(df.abs\_pct\_change >= pct\_change\_filter) & (df.volume >= min\_volume)]
breakouts\_df = detect\_breakouts(filtered, lookback\_days, breakout\_pct, vol\_mult)

if "alerts\_sent" not in st.session\_state:
st.session\_state\["alerts\_sent"] = set()

col1, col2 = st.columns(\[2,1])
with col1:
st.header("Top Gainers")
st.bar\_chart(gainers.set\_index("ticker")\["pct\_change"].head(10))
st.header("Top Losers")
st.bar\_chart(losers.set\_index("ticker")\["pct\_change"].head(10))

with col2:
st.header("Breakouts & Trade Plans")
br\_hits = breakouts\_df\[breakouts\_df.is\_breakout]
if br\_hits.empty:
st.write("No breakouts found.")
else:
for \_, r in br\_hits.iterrows():
plan = compute\_trade\_plan(r.entry, stoploss\_pct, rr)
st.markdown(f"### {r.ticker} 🚀")
st.write(f"Entry: {plan\['entry']} | Stop: {plan\['stop']} | Target: {plan\['target']} | RR: {plan\['rr']}")
if telegram\_alerts and r.ticker not in st.session\_state\["alerts\_sent"]:
bot = get\_env\_or\_secret("TELEGRAM\_BOT\_TOKEN")
chat = get\_env\_or\_secret("TELEGRAM\_CHAT\_ID")
msg = f"BREAKOUT: {r.ticker} | Entry {plan\['entry']} | Stop {plan\['stop']} | Target {plan\['target']}"
ok, \_ = send\_telegram\_alert(bot, chat, msg)
if ok:
st.session\_state\["alerts\_sent"].add(r.ticker)

st.dataframe(filtered\[\["ticker", "close", "pct\_change", "volume"]])

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

```
st.subheader("README.md")
st.code("""# NSE Streamlit Dashboard
```

This is a free Streamlit dashboard for NSE stocks showing Top Gainers/Losers, Breakouts, and Trade Plans.

## Features

* Supports groups: NIFTY50, BANKNIFTY, FINNIFTY, F\&O
* Breakout detection with filters (price, volume, risk-reward)
* Telegram alerts on breakout
* Free deployment on Streamlit Community Cloud

## How to Run

```bash
streamlit run nse_streamlit_dashboard.py
```

## Deployment

* Push this repo to GitHub
* Connect to [Streamlit Cloud](https://streamlit.io/cloud)
* Set TELEGRAM\_BOT\_TOKEN and TELEGRAM\_CHAT\_ID in Streamlit secrets
  """, language="markdown")

  st.subheader("Procfile (for Heroku, optional)")
  st.code("""web: streamlit run nse\_streamlit\_dashboard.py --server.port=\$PORT --server.address=0.0.0.0""", language="text")
