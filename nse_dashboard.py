import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import time as timer
import pytz
import base64
from datetime import datetime, time
from bs4 import BeautifulSoup
Charting_Link = "https://chartink.com/screener/"
Charting_url = 'https://chartink.com/screener/process'
group = 'cash'
# NSE headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/118.0.0.0 Safari/537.36"
}
# ----------------------
# Streamlit UI
# ----------------------
#st.set_page_config(page_title="📈 NSE Screener", layout="wide")
st.set_page_config(page_title="AJ-Algo NSE Dasboard", page_icon=":rocket:", layout="wide")
st.title("📊  AJ-Algo NSE Dasboard")

# ----------------------
# Sidebar Controls
# ----------------------
st.sidebar.title("Filters & Controls")
with st.sidebar.form("controls"):
    #group_choice = st.selectbox("Select Stock Group", list(GROUPS.keys()))
    #segment = st.sidebar.selectbox("📌 Select Market Segment", ["SECURITIES IN F&O", "NIFTY 50", "NIFTY NEXT 50"])
    segment = st.selectbox("📌 Select Market Segment", ["NIFTY 50","NIFTY & BANKNIFTY","FUTURES", "INDICES", "BANKNIFTY","EQUITY"])    
    timeFrame = st.selectbox("Select Timeframe",["5 minute","15 minute","1 hour","Daily","Weekly","Monthly"])
    pct_change_filter = st.slider("Min % change", 0.0, 20.0, 0.2, step=0.1)
    min_volume = st.number_input("Min volume", min_value=0, value=100000, step=10000)
    breakout_pct = st.slider("Breakout threshold %", 0.0, 10.0, 0.5, step=0.1)
    vol_mult = st.slider("Volume multiplier", 0.5, 5.0, 1.5, step=0.1)
    lookback_days = st.slider("Lookback days", 5, 60, 20, step=1)
    stoploss_pct = st.slider("Stoploss %", 0.1, 10.0, 2.0, step=0.1)
    rr_ratio = st.slider("Risk-Reward Ratio", 0.5, 10.0, 2.0, step=0.1)
    refresh_time = st.slider("Auto-refresh interval (mins)", 1, 60, 5)
    telegram_alerts = st.checkbox("Enable Telegram alerts")
    submit = st.form_submit_button("Apply")
    
# ----------------------    
if     segment == "NIFTY 50":          group = '33492'
elif   segment == "BANKNIFTY":         group = '136699'
elif   segment == "NIFTY & BANKNIFTY": group = '109630'
elif   segment == "INDICES":           group = '45603'
elif   segment == "FUTURES":           group = '33489'
else:                                  group = 'cash' 

# ---------------------- 
if timeFrame   == "5 minute":  timefrm = "[0] 5 minute"
elif timeFrame == "15 minute": timefrm = "[0] 15 minute"
elif timeFrame == "1 hour":    timefrm = "[0] 1 hour"
elif timeFrame == "Weekly":    timefrm = "weekly"
elif timeFrame == "Monthly":   timefrm = "monthly"
else:                          timefrm = "daily"

# ----------------------
def get_nse_gainers_losers():
    #Get condition from ChartInk by copying the Subgroup in screener
    Condition1 = '( {'+group+'} ( '+timefrm+' close > 20 ) ) '
    #Condition1 = '( {'+group+'} ( '+timefrm+' ha-open  = '+timefrm+' ha-low  ) )' 
    payload = {'scan_clause': Condition1}

    with requests.Session() as s:
        r = s.get(Charting_Link)
        soup = BeautifulSoup(r.text, "html.parser")
        csrf = soup.select_one("[name='csrf-token']")['content']
        s.headers['x-csrf-token'] = csrf
        r = s.post(Charting_url, data=payload)
        #Populate response data 'r' to dataframe
        df = pd.DataFrame()
        #print(r)
        if (r.status_code==200):
            for item in r.json()['data']:
                df = df._append(item, ignore_index=True)
                gainers = df.sort_values("per_chg", ascending=False).head(10)
                gainers1 = gainers.sort_values("per_chg", ascending=True)
                losers = df.sort_values("per_chg", ascending=True).head(10)
                losers1 = losers.sort_values("per_chg", ascending=False)
        else:
            print ('Could not fetch the data')
        return gainers1, losers1
        
# def generate_trade_plan(df, direction="long", rr_ratio=2):
#     """Generate trade plan with Risk:Reward levels"""
#     plans = []
#     for _, row in df.iterrows():
#         entry = row["lastPrice"]
#         if direction == "long":
#             stop = row["dayLow"]
#             target = entry + (entry - stop) * rr_ratio
#         else:
#             stop = row["dayHigh"]
#             target = entry - (stop - entry) * rr_ratio

#         plans.append({
#             "symbol": row["symbol"],
#             "entry": round(entry,2),
#             "stoploss": round(stop,2),
#             "target": round(target,2),
#             "risk_reward": rr_ratio
#         })
#     return pd.DataFrame(plans)

# # Streamlit UI
# st.set_page_config(page_title="📈 NSE Screener", layout="wide")
# st.title("📊 AJ-Algo NSE Dasboard")

# # ----------------------
# # Sidebar Controls
# # ----------------------
# st.sidebar.title("Filters & Controls")
# with st.sidebar.form("controls"):
#     #group_choice = st.selectbox("Select Stock Group", list(GROUPS.keys()))
#     #segment = st.sidebar.selectbox("📌 Select Market Segment", ["SECURITIES IN F&O", "NIFTY 50", "NIFTY NEXT 50"])
#     segment = st.selectbox("📌 Select Market Segment", ["nifty 50","nifty and banknifty","futures", "indices", "Banknifty","cash"])    
#     pct_change_filter = st.slider("Min % change", 0.0, 20.0, 0.2, step=0.1)
#     min_volume = st.number_input("Min volume", min_value=0, value=100000, step=10000)
#     breakout_pct = st.slider("Breakout threshold %", 0.0, 10.0, 0.5, step=0.1)
#     vol_mult = st.slider("Volume multiplier", 0.5, 5.0, 1.5, step=0.1)
#     lookback_days = st.slider("Lookback days", 5, 60, 20, step=1)
#     stoploss_pct = st.slider("Stoploss %", 0.1, 10.0, 2.0, step=0.1)
#     rr_ratio = st.slider("Risk-Reward Ratio", 0.5, 10.0, 2.0, step=0.1)
#     refresh_time = st.slider("Auto-refresh interval (mins)", 1, 60, 5)
#     telegram_alerts = st.checkbox("Enable Telegram alerts")
#     submit = st.form_submit_button("Apply")

#----------------------
#Date and Time information
#----------------------
now = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %H:%M:%S')
tim = datetime.now(pytz.timezone('Asia/Kolkata'))
timeNow    = tim.time()
dateToday  = tim.date()
day_number = tim.weekday()
# Convert the integer to a day name
days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
dayToday = days_of_week[day_number]
if dayToday != "Saturday" and dayToday != "Sunday" and timeNow>=time(9,15,0) and timeNow<=time(15,30,0) :
    nseWorking = "Open"
else:
    nseWorking = "Closed"
#----------------------
info1, info2, info3 = st.columns(3)
with info1:
    st.info(f"⚡ Screener refreshes every {refresh_time} mins")
with info2:
    st.info(f"⏰ Last Updated: {now}")
with info3:
    st.info(f"NSE is {nseWorking}")

# ✅ Always show Top 10 Gainers and Losers
gainers_df, losers_df = get_nse_gainers_losers()

col1, col2 = st.columns(2)

with col1:
    st.subheader(f"🔥 Top 10 Gainers ({segment})")
    #st.subheader("🔥 Top 10 Gainers (NIFTY 50)")
    if not gainers_df.empty:
        #st.dataframe(gainers_df[["name", "nsecode", "close", "per_chg", "volume"]])
        fig_g = px.bar(gainers_df, y="nsecode", x="per_chg",
                       title="Top Gainers % Change", color="per_chg", color_continuous_scale="Greens")
        fig_g.update_layout(
            paper_bgcolor   ='lightgray',  # Sets the background color of the entire figure
            plot_bgcolor    ='lightblue' ,  # Sets the background color of the plotting area
            autosize        = True
        )
        st.plotly_chart(fig_g)

with col2:
    st.subheader(f"💀 Top 10 Losers ({segment})")
    #st.subheader("💀 Top 10 Losers (NIFTY 50)")
    if not losers_df.empty:
        #st.dataframe(losers_df[["name", "nsecode", "close", "per_chg", "volume"]])
        fig_l = px.bar(losers_df, y="nsecode", x="per_chg",
                       title="Top Losers % Change", color="per_chg", color_continuous_scale="Reds")
        fig_l.update_layout(
            paper_bgcolor    ='lightgray',  # Sets the background color of the entire figure
            plot_bgcolor     ='lightblue',    # Sets the background color of the plotting area
            autosize         = True
        )
        st.plotly_chart(fig_l)

col3, col4 = st.columns(2)
with col3:
    st.subheader(f"Nifty")
    # Embed ChartInk chart for selected timeframe
    st.components.v1.iframe("https://chartink.com/stocks-new?symbol=NIFTY", height=600, scrolling=True)
with col4:
    st.subheader(f"BANKNIFTY")
    # Embed ChartInk chart for selected timeframe
    st.components.v1.iframe("https://chartink.com/dashboard/330461", height=600, scrolling=True)

# # 📊 Breakout Trade Plans
# st.markdown("---")
# st.subheader("📊 Breakout Trade Plans")

# gf = gainers_df[gainers_df["pChange"] >= min_change] if not gainers_df.empty else pd.DataFrame()
# lf = losers_df[losers_df["pChange"] <= -min_change] if not losers_df.empty else pd.DataFrame()

# col3, col4 = st.columns(2)

# with col3:
#     st.subheader("📈 Bullish Breakouts")
#     if not gf.empty:
#         trade_plans_long = generate_trade_plan(gf, "long", rr_ratio)
#         st.dataframe(trade_plans_long)

# with col4:
#     st.subheader("📉 Bearish Breakdowns")
#     if not lf.empty:
#         trade_plans_sh

#---------------------
# Constructing the message and sending onto telegram group with chatid and token id
if telegram_alerts == True:
    payload = {
        'chat_id': '967276571',
        #'text': f"""``` Top 5 Gainers in NIFTY50\n{tabulate(nifty50_gain_top5, headers = 'keys', tablefmt = 'pretty')}\n\n\nTop 10 Gainers in FnO Category\n{tabulate(fno_secu_gain_top10, headers = 'keys', tablefmt = 'pretty')}\n\n\nTop 10 Gainers in all securities\n{tabulate(all_secu_gain_top10, headers = 'keys', tablefmt = 'pretty')}```""",
        'text': f"""``` Top 5 Gainers in NIFTTY50```""",
        'parse_mode': 'MarkdownV2'}
    tokenid = '8290350450:AAHR7QvcVTp_IMpFcHhZsgeIaNyBSGTe9Q0'
    url = f'https://api.telegram.org/bot{tokenid}/sendmessage'
    requests.post(url,data=payload,verify=False)
#---------------------

timer.sleep(refresh_time * 60)
st.rerun()
