import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="Gold Strategy Pro v2", page_icon="💰", layout="centered")

class GoldBotMobile:
    def __init__(self):
        self.weights = {'^GSPC': 0.50, '^GDAXI': 0.20, '000001.SS': 0.15, '^N225': 0.15}
        self.gold_ticker = 'GC=F'
        self.vix_ticker = '^VIX'

    def fetch_data(self):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=60)
        tickers = list(self.weights.keys()) + [self.gold_ticker, self.vix_ticker]
        data = yf.download(tickers, start=start_date, end=end_date, progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            data = data['Close']
        return data.ffill().dropna()

    def calculate_metrics(self, data):
        gmsi = (data['^GSPC'] * 0.50) + (data['^GDAXI'] * 0.20) + (data['000001.SS'] * 0.15) + (data['^N225'] * 0.15)
        gold = data[self.gold_ticker]
        ratio = gold / gmsi
        
        high_low = data[self.gold_ticker].rolling(2).max() - data[self.gold_ticker].rolling(2).min()
        atr = high_low.rolling(14).mean().iloc[-1]
        
        return gmsi, gold, ratio, atr

    def get_dynamic_config(self, price, atr, balance):
        vola_pct = (atr / price) * 100
        if vola_pct < 0.8:
            lev = 7
        elif vola_pct < 1.5:
            lev = 5
        elif vola_pct < 2.5:
            lev = 2
        else:
            lev = 1
        
        if balance > 25000:
            lev = min(lev, 3)
        if balance > 50000:
            lev = min(lev, 2)
            
        return lev, atr * 2

bot = GoldBotMobile()

st.markdown("""
<style>
    .stApp { background-color: #0E1117 !important; }
    h1, h2, h3, p, span, label, .stMarkdown { color: #FFFFFF !important; }
    [data-testid="stMetricValue"] { color: #FFFFFF !important; font-size: 1.8rem !important; font-weight: bold !important; }
    [data-testid="stMetricLabel"] { color: #FFD700 !important; font-size: 1rem !important; }
    div[data-testid="stMetric"] { background-color: #1F2937 !important; border: 2px solid #FFD700 !important; padding: 15px !important; border-radius: 10px !important; }
    .stNumberInput input { background-color: #1F2937 !important; color: #FFFFFF !important; }
    .stButton>button { width: 100% !important; background-color: #FFD700 !important; color: #000000 !important; font-weight: bold !important; border-radius: 10px !important; height: 3em !important; }
</style>
""", unsafe_allow_html=True)

st.title("💰 Gold Strategie Pro v2")
st.markdown("---")

kapital = st.number_input("Dein Kapital (CHF)", value=5000.0, step=100.0)
pl = st.number_input("Gewinn/Verlust (+/-)", value=0.0, step=10.0)
kontostand = kapital + pl

st.metric("Aktueller Kontostand", f"{kontostand:.2f} CHF")

if st.button("MARKT JETZT ANALYSIEREN"):
    df = bot.fetch_data()
    if not df.empty:
        gmsi_series, gold_series, ratio_series, atr = bot.calculate_metrics(df)
        
        current_gold = gold_series.iloc[-1]
        current_gmsi = gmsi_series.iloc[-1]
        current_vix = df[bot.vix_ticker].iloc[-1]
        current_ratio = ratio_series.iloc[-1]
        ratio_sma = ratio_series.rolling(20).mean().iloc[-1]
        
        leverage, sl_dist = bot.get_dynamic_config(current_gold, atr, kontostand)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Goldpreis", f"${current_gold:.2f}")
            st.metric("Gold-Ratio", f"{current_ratio:.4f}")
        with col2:
            st.metric("VIX Index", f"{current_vix:.2f}")
            st.metric("Dyn. Hebel", f"{leverage}x")

        st.markdown(f"### Strategische Analyse")
        st.latex(r"Ratio = \frac{Gold_{Price}}{GMSI}")

        is_long = (current_gmsi < gmsi_series.rolling(20).mean().iloc[-1]) and (current_ratio > ratio_sma)
        is_short = (current_gmsi > gmsi_series.rolling(20).mean().iloc[-1]) and (current_ratio < ratio_sma)

        if is_long:
            sig_text, sig_col, order_type = "KAUFEN (LONG)", "green", "BUY"
            final_sl = current_gold - sl_dist
        elif is_short:
            sig_text, sig_col, order_type = "VERKAUFEN (SHORT)", "red", "SELL"
            final_sl = current_gold + sl_dist
        else:
            sig_text, sig_col, order_type = "NEUTRAL (WARTEN)", "gray", "NONE"

        if order_type != "NONE":
            t212_value = kontostand * leverage
            st.info(f"""
            **Trading 212 Anweisung ({sig_text}):**
            - **Richtung:** {order_type}
            - **Positions-Wert:** {t212_value:.2f} CHF
            - **Stop-Loss:** ${final_sl:.2f}
            - **Aktueller ATR-Stop:** ${sl_dist:.2f}
            """)
            st.success(f"**SIGNAL: {sig_text}**")
        else:
            st.error("**SIGNAL: KEIN EINSTIEG (MARKT UNSICHER)**")
