import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

if 'history' not in st.session_state:
    st.session_state.history = []

class GoldBotPro:
    def __init__(self):
        self.weights = {'S&P 500 (^GSPC)': 0.50, 'DAX (^GDAXI)': 0.20, 'SSE Composite (000001.SS)': 0.15, 'Nikkei 225 (^N225)': 0.15}
        self.tickers = ['^GSPC', '^GDAXI', '000001.SS', '^N225', 'GC=F', '^VIX']

    def get_data(self):
        data = yf.download(self.tickers, period="60d", interval="1d", progress=False)['Close']
        return data.ffill().dropna()

    def calc_gmsi(self, df):
        return (df['^GSPC'] * 0.50) + (df['^GDAXI'] * 0.20) + (df['000001.SS'] * 0.15) + (df['^N225'] * 0.15)

    def get_config(self, price, atr, balance):
        vola = (atr / price) * 100
        lev = 7 if vola < 0.8 else 5 if vola < 1.5 else 2 if vola < 2.5 else 1
        if balance > 25000: lev = min(lev, 3)
        return lev, atr * 2, atr * 4

bot = GoldBotPro()

st.title("💰 Gold Strategie Pro: Terminal")

with st.expander("📊 Datenquellen & Gewichtung (GMSI)"):
    st.write("Der Global Market Sentiment Index setzt sich zusammen aus:")
    st.table(pd.DataFrame([{"Index": k, "Gewichtung": f"{v*100}%"} for k, v in bot.weights.items()]))
    st.caption("Quelle: Yahoo Finance Echtzeit-Daten")

st.sidebar.header("Konto-Verwaltung")
kapital = st.sidebar.number_input("Startkapital (CHF)", value=5000.0)
current_balance = kapital + sum([t['profit'] for t in st.session_state.history])
st.sidebar.metric("Echtzeit-Kontostand", f"{current_balance:.2f} CHF")

if st.button("🚀 ANALYSE STARTEN"):
    df = bot.get_data()
    gmsi = bot.calc_gmsi(df)
    gold = df['GC=F']
    ratio = gold / gmsi
    atr = (gold.rolling(2).max() - gold.rolling(2).min()).rolling(14).mean().iloc[-1]
    
    lev, sl_dist, tp_dist = bot.get_config(gold.iloc[-1], atr, current_balance)
    
    is_long = (gmsi.iloc[-1] < gmsi.rolling(20).mean().iloc[-1]) and (ratio.iloc[-1] > ratio.rolling(20).mean().iloc[-1])
    is_short = (gmsi.iloc[-1] > gmsi.rolling(20).mean().iloc[-1]) and (ratio.iloc[-1] < ratio.rolling(20).mean().iloc[-1])
    
    direction = "KAUFEN (LONG)" if is_long else "VERKAUFEN (SHORT)" if is_short else "NEUTRAL"
    color = "green" if is_long else "red" if is_short else "white"
    
    st.markdown(f"### Signal: <span style='color:{color}'>{direction}</span>", unsafe_allow_html=True)
    
    if direction != "NEUTRAL":
        volumen = current_balance * lev
        entry = gold.iloc[-1]
        sl = entry - sl_dist if is_long else entry + sl_dist
        tp = entry + tp_dist if is_long else entry - tp_dist
        
        st.subheader("📝 Trading 212 Eingabe-Befehl")
        col_a, col_b = st.columns(2)
        with col_a:
            st.warning(f"**RICHTUNG:** {direction.split()[0]}")
            st.write(f"**VOLUMEN:** {volumen:.2f} CHF")
        with col_b:
            st.write(f"**STOP-LOSS:** ${sl:.2f}")
            st.write(f"**TAKE-PROFIT:** ${tp:.2f}")
            
        st.session_state.last_trade = {"type": direction.split()[0], "entry": entry, "vol": volumen, "lev": lev}

st.divider()

st.subheader("📈 Trade-Logger & Historie")
if 'last_trade' in st.session_state:
    res_col1, res_col2 = st.columns(2)
    with res_col1:
        profit_input = st.number_input("Resultat (CHF Gewinn/Verlust)", value=0.0)
    with res_col2:
        if st.button("Trade in Historie speichern"):
            st.session_state.history.append({
                "date": datetime.now().strftime("%d.%m.%Y"),
                "type": st.session_state.last_trade['type'],
                "profit": profit_input
            })
            st.success("Trade gespeichert!")

if st.session_state.history:
    hist_df = pd.DataFrame(st.session_state.history)
    st.table(hist_df)
    
    win_rate = (len(hist_df[hist_df['profit'] > 0]) / len(hist_df)) * 100
    total_p = hist_df['profit'].sum()
    
    stat_col1, stat_col2 = st.columns(2)
    stat_col1.metric("Gesamtprofit", f"{total_p:.2f} CHF")
    stat_col2.metric("Win-Rate", f"{win_rate:.1%}")
else:
    st.info("Noch keine Trades in der Historie vorhanden.")
