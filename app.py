import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="Gold Strategy Pro", page_icon="💰", layout="centered")

class GoldBotMobile:
    def __init__(self, leverage=5, stop_loss_pct=0.035):
        self.leverage = leverage
        self.stop_loss_pct = stop_loss_pct
        self.weights = {'^GSPC': 0.50, '^GDAXI': 0.20, '000001.SS': 0.15, '^N225': 0.15}
        self.gold_ticker = 'GC=F'
        self.vix_ticker = '^VIX'

    def fetch_data(self):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)
        tickers = list(self.weights.keys()) + [self.gold_ticker, self.vix_ticker]
        data = yf.download(tickers, start=start_date, end=end_date, progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            data = data['Adj Close'] if 'Adj Close' in data.columns.levels[0] else data['Close']
        return data.ffill().dropna()

bot = GoldBotMobile()

st.markdown("""
<style>
    .stApp {
        background-color: #0E1117 !important;
    }
    h1, h2, h3, p, span, label, .stMarkdown {
        color: #FFFFFF !important;
    }
    [data-testid="stMetricValue"] {
        color: #FFFFFF !important;
        font-size: 1.8rem !important;
        font-weight: bold !important;
    }
    [data-testid="stMetricLabel"] {
        color: #FFD700 !important;
        font-size: 1rem !important;
        text-transform: uppercase !important;
    }
    div[data-testid="stMetric"] {
        background-color: #1F2937 !important;
        border: 2px solid #FFD700 !important;
        padding: 15px !important;
        border-radius: 10px !important;
    }
    .stNumberInput input {
        background-color: #1F2937 !important;
        color: #FFFFFF !important;
        border: 1px solid #4B5563 !important;
    }
    .stButton>button {
        width: 100% !important;
        background-color: #FFD700 !important;
        color: #000000 !important;
        font-weight: bold !important;
        font-size: 1.2rem !important;
        border-radius: 10px !important;
        height: 3em !important;
        margin-top: 10px !important;
    }
    .stAlert {
        background-color: #1F2937 !important;
        color: #FFFFFF !important;
        border: 1px solid #FFD700 !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("💰 Gold Strategie Pro")
st.markdown("---")

kapital = st.number_input("Dein Kapital (CHF)", value=3000.0, step=100.0)
pl = st.number_input("Gewinn/Verlust (+/-)", value=0.0, step=10.0)
kontostand = kapital + pl

st.metric("Aktueller Kontostand", f"{kontostand:.2f} CHF")

if st.button("MARKT JETZT ANALYSIEREN"):
    data = bot.fetch_data()
    if not data.empty:
        last = data.iloc[-1]
        prev = data.iloc[-2]
        
        gmsi_last = (last['^GSPC'] * 0.50) + (last['^GDAXI'] * 0.20) + (last['000001.SS'] * 0.15) + (last['^N225'] * 0.15)
        gmsi_prev = (prev['^GSPC'] * 0.50) + (prev['^GDAXI'] * 0.20) + (prev['000001.SS'] * 0.15) + (prev['^N225'] * 0.15)
        
        gold_price = last[bot.gold_ticker]
        vix = last[bot.vix_ticker]
        
        gmsi_chg = (gmsi_last - gmsi_prev) / gmsi_prev
        gold_chg = (gold_price - prev[bot.gold_ticker]) / prev[bot.gold_ticker]
        
        t212_value = kontostand * bot.leverage
        sl_price = gold_price * (1 - bot.stop_loss_pct)
        risk_chf = kontostand * (bot.stop_loss_pct * bot.leverage)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Goldpreis", f"${gold_price:.2f}")
        with col2:
            st.metric("VIX Index", f"{vix:.2f}")
        
        st.subheader("Trading 212 Anweisung:")
        st.info(f"""
        **1. Modus:** WERT (CHF)  
        **2. Betrag:** {t212_value:.2f} CHF  
        **3. Stop-Loss Preis:** ${sl_price:.2f}  
        **4. Risiko:** -{risk_chf:.2f} CHF
        """)
        
        is_crisis = gmsi_chg < -0.008 and gold_chg >= -0.002 and vix > 20
        is_infl = gmsi_chg > 0.005 and gold_chg > 0.005
        
        if is_crisis or is_infl:
            st.success("GLASKLARE ANTWORT: KAUFEN")
        else:
            st.error("GLASKLARE ANTWORT: NICHT KAUFEN")