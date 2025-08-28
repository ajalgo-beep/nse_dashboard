# nse_dashboard.py
import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from time import sleep
from typing import Tuple

# ---------------------------
# Basic configuration
# ---------------------------
st.set_page_config(page_title="📈 NSE Dashboard", layout="wide")
st.title("📊 NSE Full Dashboard — Gainers, F&O, Option Chain & Trade Plans")

# NSE headers (helps avoid 403)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/118.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}

# ---------------------------
# Utility: session with cookie preload
# ---------------------------
def nse_session(timeout=10):
    """Return a requests.Session preloaded with NSE cookies and headers."""
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        # Preload cookies (sometimes necessary)
        session.get("https://www.nseindia.com", timeout=timeout)
    except Exception:
        # Non-fatal — continue, the subsequent calls will attempt anyway.
        pass
    return session

# ---------------------------
# Caching wrappers
# ---------------------------
@st.cache_data(ttl=60)  # short caching; refresh often in a trading app
def fetch_json(url: str, params=None, timeout=10):
    s = nse_session()
    resp = s.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

# ---------------------------
# Data fetchers
# ---------------------------
@st.cache_data(ttl=60)
def get_nifty50_members() -> pd.DataFrame:
    """
    Get NIFTY 50 constituents table (name, symbol, lastPrice, pChange etc.)
    Uses the NSE index API for NIFTY 50.
    """
    url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050"
    try:
        data = fetch_json(url)
        df = pd.DataFrame(data.get("data", []))
        # normalize numeric columns
        for col in ["lastPrice", "pChange", "dayHigh", "dayLow", "totalTradedValue"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except Exception as e:
        st.error(f"Error fetching NIFTY 50 members: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def get_indices_snapshot() -> pd.DataFrame:
    """
    Fetch major index snapshots. We attempt multiple known endpoints.
    """
    # Example: NSE has a summary endpoint for indices (works for many indices)
    url = "https://www.nseindia.com/api/allIndices"
    try:
        data = fetch_json(url)
        df = pd.DataFrame(data.get("data", []))
        # numeric conversions
        for c in ["last", "change", "pChange", "points"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
        return df
    except Exception as e:
        st.error(f"Error fetching indices snapshot: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def get_top_movers(n=10) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Return top n gainers and losers for NIFTY 50 (based on pChange).
    """
    df = get_nifty50_members()
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()
    df = df.dropna(subset=["pChange"])
    gainers = df.sort_values("pChange", ascending=False).head(n)
    losers = df.sort_values("pChange", ascending=True).head(n)
    return gainers, losers

@st.cache_data(ttl=60)
def get_sector_performance():
    """
    Attempt to get sector performance. NSE endpoint for sector may vary; we try the known path.
    """
    url = "https://www.nseindia.com/api/sectorPerformance"  # may or may not exist
    try:
        data = fetch_json(url)
        df = pd.DataFrame(data.get("data", []))
        return df
    except Exception:
        # fallback: empty DataFrame
        return pd.DataFrame()

@st.cache_data(ttl=30)
def get_option_chain_index(symbol: str = "NIFTY") -> pd.DataFrame:
    """
    Fetch option chain for an index symbol (e.g., NIFTY, BANKNIFTY)
    Endpoint: /api/option-chain-indices?symbol=...
    """
    url = "https://www.nseindia.com/api/option-chain-indices"
    try:
        data = fetch_json(url, params={"symbol": symbol})
        records = data.get("records", {})
        underlying = records.get("underlyingValue", None)
        all_data = []
        for rec in records.get("data", []):
            strike = rec.get("strikePrice")
            ce = rec.get("CE", {})
            pe = rec.get("PE", {})
            # merge CE and PE with strike
            row = {"strike": strike, "underlying": underlying}
            # CE fields
            for k, v in ce.items():
                row[f"CE_{k}"] = v
            for k, v in pe.items():
                row[f"PE_{k}"] = v
            all_data.append(row)
        df = pd.DataFrame(all_data)
        return df
    except Exception as e:
        st.warning(f"Option chain fetch issue: {e}")
        return pd.DataFrame()

# ---------------------------
# Chart helpers
# ---------------------------
def plot_candlestick(df_ohlc: pd.DataFrame, title="Intraday Candle"):
    """
    df_ohlc expects columns: datetime (pd.Datetime), open, high, low, close, volume(optional)
    """
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df_ohlc['datetime'],
        open=df_ohlc['open'],
        high=df_ohlc['high'],
        low=df_ohlc['low'],
        close=df_ohlc['close'],
        name='price'
    ))
    if 'volume' in df_ohlc.columns:
        fig.add_trace(go.Bar(x=df_ohlc['datetime'], y=df_ohlc['volume'], name='volume', yaxis='y2', marker={'opacity':0.3}))
        # secondary y-axis
        fig.update_layout(
            yaxis2=dict(overlaying='y', side='right', showgrid=False, title='Volume', position=0.98, rangemode='tozero'),
            margin=dict(t=40, b=40)
        )
    fig.update_layout(title=title, xaxis_rangeslider_visible=False, height=520)
    return fig

# ---------------------------
# Trade Plan generator (based on reference)
# ---------------------------
def generate_trade_plan(df: pd.DataFrame, direction="long", rr_ratio=2.0) -> pd.DataFrame:
    plans = []
    for _, row in df.iterrows():
        try:
            entry = float(row.get("lastPrice", row.get("underlying", 0)))
            # fallback dayLow/dayHigh if present
            if direction == "long":
                stop = float(row.get("dayLow", entry * 0.995))  # fallback to small buffer if dayLow missing
                target = entry + (entry - stop) * rr_ratio
            else:
                stop = float(row.get("dayHigh", entry * 1.005))
                target = entry - (stop - entry) * rr_ratio
            plans.append({
                "symbol": row.get("symbol", row.get("name", "")),
                "entry": round(entry, 2),
                "stoploss": round(stop, 2),
                "target": round(target, 2),
                "risk_reward": rr_ratio
            })
        except Exception:
            continue
    return pd.DataFrame(plans)

# ---------------------------
# Intraday data fetch (yfinance fallback)
# ---------------------------
def fetch_intraday_yfinance(symbol: str, period="1d", interval="5m") -> pd.DataFrame:
    """Use yfinance to fetch intraday OHLC if nse endpoints are unavailable.
    The user must have yfinance installed in the environment."""
    try:
        import yfinance as yf
        # For NSE: append .NS to symbol if not already present
        yf_symbol = symbol if (symbol.endswith(".NS") or symbol.endswith(".BO")) else f"{symbol}.NS"
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period=period, interval=interval)
        if hist.empty:
            return pd.DataFrame()
        hist = hist.reset_index()
        hist = hist.rename(columns={"Datetime": "datetime", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        # sometimes column names differ
        if 'Date' in hist.columns:
            hist = hist.rename(columns={'Date': 'datetime'})
        hist['datetime'] = pd.to_datetime(hist['datetime'])
        # ensure required cols
        return hist[['datetime', 'open', 'high', 'low', 'close', 'volume']]
    except Exception as e:
        st.warning("yfinance intraday fetch failed or yfinance not installed: " + str(e))
        return pd.DataFrame()

# ---------------------------
# Sidebar controls
# ---------------------------
with st.sidebar:
    st.header("Controls")
    min_change = st.slider("Min % Change for Breakouts", 0.5, 10.0, 2.0, 0.1)
    rr_ratio = st.slider("Risk:Reward Ratio", 1.0, 5.0, 2.0, 0.5)
    refresh_min = st.slider("Auto-refresh (secs)", 30, 600, 120, 10)
    symbol_search = st.text_input("Search symbol (e.g., RELIANCE or NIFTY)", value="NIFTY")
    opt_symbol = st.selectbox("Option Chain Symbol", options=["NIFTY", "BANKNIFTY"], index=0)
    show_sector = st.checkbox("Show Sector Performance", value=True)
    show_indices = st.checkbox("Show Indices Snapshot", value=True)

# auto refresh mechanism — simple counter + rerun pattern
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = datetime.now()

# top row: indices summary + refresh info
cols = st.columns([3, 1])
with cols[0]:
    if show_indices:
        idx_df = get_indices_snapshot()
        if not idx_df.empty:
            # pick a few key indices to show in-line
            key_indices = idx_df[idx_df['indexName'].isin(["NIFTY 50", "S&P BSE SENSEX", "NIFTY Bank"])]
            if key_indices.empty:
                key_indices = idx_df.head(6)
            # neat display: cards
            cards = []
            for _, r in key_indices.iterrows():
                kpi = f"{r.get('last'):.2f}" if pd.notnull(r.get('last')) else "N/A"
                pch = r.get('pChange', None)
                delta = f"{pch:.2f}%" if pd.notnull(pch) else "N/A"
                cards.append((r.get('indexName', ''), kpi, delta))
            # show horizontally
            cols_cards = st.columns(len(cards))
            for c, card in zip(cols_cards, cards):
                name, val, pct = card
                c.metric(label=name, value=val, delta=pct)
        else:
            st.write("Indices snapshot unavailable")
with cols[1]:
    st.write(f"Last refresh: {st.session_state.last_refresh.strftime('%Y-%m-%d %H:%M:%S')}")
    if st.button("Refresh Now"):
        st.session_state.last_refresh = datetime.now()
        st.experimental_rerun()

# ---------------------------
# Main layout: Movers, Sector, Option chain, Intraday Charts
# ---------------------------
left_col, right_col = st.columns([2, 3])

# Left column: Top movers + trade plan
with left_col:
    st.subheader("🔥 Top Movers (NIFTY 50)")
    gainers_df, losers_df = get_top_movers(n=15)
    gm, lm = st.tabs(["Gainers", "Losers"])
    with gm:
        if not gainers_df.empty:
            st.dataframe(gainers_df[["symbol", "lastPrice", "pChange", "dayHigh", "dayLow", "totalTradedValue"]].reset_index(drop=True))
            fig = px.bar(gainers_df, x="symbol", y="pChange", color="pChange", color_continuous_scale="Greens", title="Top Gainers % Change")
            st.plotly_chart(fig, use_container_width=True)
            # breakout filter
            gf = gainers_df[gainers_df["pChange"] >= min_change]
            if not gf.empty:
                st.markdown("**Bullish Breakout Candidates**")
                tp_long = generate_trade_plan(gf, "long", rr_ratio)
                st.dataframe(tp_long)
                st.download_button("Export Bullish Plans CSV", tp_long.to_csv(index=False), "bullish_plans.csv")
        else:
            st.write("No data")

    with lm:
        if not losers_df.empty:
            st.dataframe(losers_df[["symbol", "lastPrice", "pChange", "dayHigh", "dayLow", "totalTradedValue"]].reset_index(drop=True))
            fig2 = px.bar(losers_df, x="symbol", y="pChange", color="pChange", color_continuous_scale="Reds", title="Top Losers % Change")
            st.plotly_chart(fig2, use_container_width=True)
            lf = losers_df[losers_df["pChange"] <= -min_change]
            if not lf.empty:
                st.markdown("**Bearish Breakdown Candidates**")
                tp_short = generate_trade_plan(lf, "short", rr_ratio)
                st.dataframe(tp_short)
                st.download_button("Export Bearish Plans CSV", tp_short.to_csv(index=False), "bearish_plans.csv")
        else:
            st.write("No data")

    # Sector performance
    if show_sector:
        st.markdown("---")
        st.subheader("📊 Sector Performance (if available)")
        sector_df = get_sector_performance()
        if not sector_df.empty:
            st.dataframe(sector_df)
            fig_s = px.bar(sector_df, x='sector', y='change', color='change', color_continuous_scale='Viridis', title="Sector Change (%)")
            st.plotly_chart(fig_s, use_container_width=True)
        else:
            st.write("Sector performance data not available via current endpoint.")

# Right column: Option chain & Intraday charts
with right_col:
    st.subheader("🧾 Option Chain Viewer")
    oc = get_option_chain_index(opt_symbol)
    if not oc.empty:
        st.write(f"Underlying value: {oc['underlying'].iloc[0] if 'underlying' in oc.columns else 'N/A'}")
        # show nearest strikes around underlying
        underlying = float(oc['underlying'].iloc[0]) if 'underlying' in oc.columns and pd.notnull(oc['underlying'].iloc[0]) else None
        if underlying is not None:
            # select strikes within +/- 20 strikes or price-range
            strikes = oc['strike'].dropna().unique()
            strikes = sorted(list(strikes))
            # find nearest strike index
            closest = min(strikes, key=lambda x: abs(x - underlying)) if strikes else None
            idx = strikes.index(closest) if closest in strikes else 0
            window = 10
            low = max(0, idx-window)
            high = min(len(strikes), idx+window)
            subset = oc[oc['strike'].isin(strikes[low:high])]
            st.dataframe(subset.sort_values('strike').reset_index(drop=True))
            # simple visualization: OI for calls vs puts across strikes
            # some fields may be missing; try safe access
            if not subset.empty:
                subset_plot = subset.copy()
                subset_plot['CE_OI'] = pd.to_numeric(subset_plot.get('CE_openInterest', 0), errors='coerce').fillna(0)
                subset_plot['PE_OI'] = pd.to_numeric(subset_plot.get('PE_openInterest', 0), errors='coerce').fillna(0)
                fig_oc = go.Figure()
                fig_oc.add_trace(go.Bar(x=subset_plot['strike'], y=subset_plot['CE_OI'], name='Call OI', marker_color='green'))
                fig_oc.add_trace(go.Bar(x=subset_plot['strike'], y=subset_plot['PE_OI'], name='Put OI', marker_color='red'))
                fig_oc.update_layout(title=f"Option OI by Strike ({opt_symbol})", barmode='group', xaxis_title="Strike", yaxis_title="Open Interest")
                st.plotly_chart(fig_oc, use_container_width=True)
        else:
            st.write("Option chain returned but underlying value missing.")
    else:
        st.info("Option chain not available for selected symbol.")

    st.markdown("---")
    st.subheader("📈 Intraday Chart / Symbol Lookup")
    sym = symbol_search.strip().upper()
    st.write(f"Symbol: {sym}")
    # attempt to get intraday via yfinance (user must have yfinance installed)
    intraday = fetch_intraday_yfinance(sym, period="1d", interval="5m")
    if not intraday.empty:
        fig_c = plot_candlestick(intraday, title=f"{sym} Intraday (5m)")
        st.plotly_chart(fig_c, use_container_width=True)
    else:
        st.info("Intraday data not available via yfinance or symbol may not exist. Try an NSE stock symbol (e.g., RELIANCE) or install yfinance.")

# ---------------------------
# Footer: helpful tips and export
# ---------------------------
st.markdown("---")
st.write("Tips:")
st.write("- If any NSE endpoints return 403/blocked, ensure your server IP and headers are acceptable to NSE and that you preload cookies.")
st.write("- yfinance fallback used for intraday data; install with `pip install yfinance` on your machine.")
st.write("- This dashboard is for educational/screening purposes. Backtest & verify before trading.")

# Auto refresh logic (will rerun the app at intervals)
def auto_refresh(seconds: int):
    """
    Very simple auto refresh using Streamlit experimental rerun.
    The logic only triggers when enough seconds have passed since last_refresh.
    """
    last = st.session_state.get("last_refresh", datetime.min)
    if (datetime.now() - last).total_seconds() > seconds:
        st.session_state.last_refresh = datetime.now()
        st.experimental_rerun()

# activate auto refresh (only if user set > 0)
if refresh_min and refresh_min > 0:
    # refresh_min is in seconds here (from slider)
    auto_refresh(refresh_min)

