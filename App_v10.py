import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime
import pytz

st.set_page_config(page_title="Multi-Commodity Pro Terminal", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0f172a; color: #f8fafc; }
    .stMetric { background-color: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 15px; }
    .stButton>button { background-color: #3b82f6 !important; color: white !important; border-radius: 5px; width: 100%; height: 3em; font-weight: bold; border: none; }
    .stExpander { border: 1px solid #334155 !important; border-radius: 10px !important; background-color: #1e293b !important; }
    .order-label { color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; margin-bottom: 0px; }
    .order-value { color: #f8fafc; font-size: 1.1rem; font-weight: bold; margin-top: 0px; }
    .stInfo { background-color: #0c4a6e; border: 1px solid #075985; color: #e0f2fe; }
    .stSuccess { background-color: #064e3b; border: 1px solid #065f46; color: #ecfdf5; }
    .stWarning { background-color: #451a03; border: 1px solid #78350f; color: #fff7ed; }
    .stError { background-color: #450a0a; border: 1px solid #7f1d1d; color: #fef2f2; }
    h1, h2, h3 { color: #f8fafc !important; }
    </style>
""", unsafe_allow_html=True)

def get_market_context():
    tz_zurich = pytz.timezone('Europe/Zurich')
    now = datetime.now(tz_zurich)
    current_hour = now.hour
    weekday = now.weekday()
    if weekday >= 5:
        status, color, rec = "GESCHLOSSEN", "red", "Wochenende. Märkte öffnen Sonntag 24:00."
    elif current_hour == 23:
        status, color, rec = "PAUSE", "orange", "Täglicher Gap. Warte bis 00:00."
    elif 5 <= current_hour < 7:
        status, color, rec = "OPTIMAL", "green", "Asien-Session. Beste Zeit für dein Gebot."
    else:
        status, color, rec = "AKTIV", "blue", "Regulärer Handel aktiv."
    exit_time = "22:30" if weekday == 4 else "22:45"
    return {"time": now.strftime("%H:%M:%S"), "status": status, "color": color, "rec": rec, "exit": exit_time}

def load_history():
    if os.path.exists('trade_history.csv'):
        return pd.read_csv('trade_history.csv')
    return pd.DataFrame(columns=['Datum', 'Rohstoff', 'Typ', 'Einstieg', 'Hebel', 'Gewinn_CHF'])

def save_to_history(df, entry):
    df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
    df.to_csv('trade_history.csv', index=False)
    return df

class TradingEngine:
    def __init__(self):
        self.weights_std = {'^GSPC': 0.50, '^GDAXI': 0.20, '000001.SS': 0.15, '^N225': 0.15}
        self.weights_eco = {'^GSPC': 0.35, '^GDAXI': 0.20, '000001.SS': 0.30, '^N225': 0.15}
        self.weights_crisis = {'^GSPC': 0.80, '^GDAXI': 0.10, '000001.SS': 0.05, '^N225': 0.05}
        self.assets = {'GOLD': 'GC=F', 'SILBER': 'SI=F', 'WTI_ÖL': 'CL=F', 'KUPFER': 'HG=F', 'PLATIN': 'PL=F'}

    def fetch_data(self):
        tickers = list(self.weights_std.keys()) + list(self.assets.values()) + ['^VIX']
        data = yf.download(tickers, period="60d", interval="1d", progress=False)['Close']
        data = data.ffill().dropna()
        
        for asset_name, ticker in self.assets.items():
            live_data = yf.download(ticker, period="1d", interval="1m", progress=False)['Close']
            if not live_data.empty:
                val = live_data.iloc[-1]
                if isinstance(val, pd.Series):
                    val = val.iloc[0]
                data.loc[data.index[-1], ticker] = float(val)
                
        return data

    def calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def get_signal(self, name, current_gmsi, gmsi_sma, current_ratio, ratio_sma, current_vix, rsi):
        vix_panic = current_vix > 25
        if name in ['GOLD', 'SILBER', 'PLATIN']:
            if (current_gmsi < gmsi_sma or vix_panic) and current_ratio > ratio_sma and rsi < 70: return 'LONG'
            if current_gmsi > gmsi_sma and current_ratio < ratio_sma and rsi > 30: return 'SHORT'
        elif name in ['WTI_ÖL', 'KUPFER']:
            if current_gmsi > gmsi_sma and current_ratio < ratio_sma and rsi < 70: return 'LONG'
            if current_gmsi < gmsi_sma and current_ratio > ratio_sma and rsi > 30: return 'SHORT'
        return 'HOLD'

engine = TradingEngine()
history_df = load_history()
ctx = get_market_context()

st.title("💰 Multi-Commodity Pro Terminal")
st.markdown(f"**Zeit:** {ctx['time']} | **Status:** :{ctx['color']}[{ctx['status']}]")

col_main, col_depot = st.columns([2, 1])

with col_depot:
    st.header("🏦 Depot")
    start_kap = st.number_input("Startkapital (CHF)", value=5000.0)
    total_p = history_df['Gewinn_CHF'].sum() if not history_df.empty else 0.0
    current_bal = start_kap + total_p
    st.metric("Kontostand", f"{current_bal:.2f} CHF", delta=f"{total_p:.2f} CHF")
    st.divider()
    with st.form("logger"):
        log_asset = st.selectbox("Rohstoff", list(engine.assets.keys()))
        log_dir = st.selectbox("Richtung", ["LONG", "SHORT"])
        log_price = st.number_input("Einstieg ($)", value=0.0)
        log_lev = st.number_input("Hebel", value=1)
        log_res = st.number_input("Gewinn/Verlust (CHF)", value=0.0)
        if st.form_submit_button("Trade loggen"):
            history_df = save_to_history(history_df, {
                'Datum': datetime.now().strftime("%Y-%m-%d"),
                'Rohstoff': log_asset,
                'Typ': log_dir,
                'Einstieg': log_price,
                'Hebel': log_lev,
                'Gewinn_CHF': log_res
            })
            st.rerun()

with col_main:
    if st.button("🔍 ALLE ROHSTOFFE ANALYSIEREN"):
        df = engine.fetch_data()
        vix_val = df['^VIX'].iloc[-1]
        results = []
        for name, ticker in engine.assets.items():
            if vix_val > 25:
                w = engine.weights_crisis
            elif name in ['KUPFER', 'WTI_ÖL']:
                w = engine.weights_eco
            else:
                w = engine.weights_std
            
            gmsi_series = (df['^GSPC'] * w['^GSPC']) + (df['^GDAXI'] * w['^GDAXI']) + (df['000001.SS'] * w['000001.SS']) + (df['^N225'] * w['^N225'])
            gmsi_val = gmsi_series.iloc[-1]
            gmsi_sma = gmsi_series.rolling(20).mean().iloc[-1]
            price_s = df[ticker]
            price = price_s.iloc[-1]
            rsi = engine.calculate_rsi(price_s).iloc[-1]
            ratio = price / gmsi_val
            ratio_sma = (price_s / gmsi_series).rolling(20).mean().iloc[-1]
            atr = (price_s.rolling(2).max() - price_s.rolling(2).min()).rolling(14).mean().iloc[-1]
            sig = engine.get_signal(name, gmsi_val, gmsi_sma, ratio, ratio_sma, vix_val, rsi)
            results.append({'name': name, 'price': price, 'ratio': ratio, 'ratio_sma': ratio_sma, 'atr': atr, 'sig': sig, 'rsi': rsi})
            
        active_signals = [r for r in results if r['sig'] != 'HOLD']
        num_active = len(active_signals)
        capital_per_trade = current_bal / num_active if num_active > 0 else current_bal
        
        for res in results:
            name, price, atr, sig, rsi = res['name'], res['price'], res['atr'], res['sig'], res['rsi']
            final_dir = sig if sig != 'HOLD' else ('LONG' if res['ratio'] > res['ratio_sma'] else 'SHORT')
            is_ready = sig != 'HOLD'
            
            with st.expander(f"{'✅ ' if is_ready else '📊 '}{name}", expanded=is_ready):
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Preis", f"${price:.2f}")
                m2.metric("Trend", "BULLISH" if res['ratio'] > res['ratio_sma'] else "BEARISH")
                m3.metric("Signal", sig)
                m4.metric("RSI", f"{rsi:.1f}")
                
                st.markdown("---")
                r1, r2, r3 = st.columns(3)
                r1.markdown(f'<p class="order-label">Richtung</p><p class="order-value" style="color:{"#10B981" if final_dir == "LONG" else "#EF4444"}">{final_dir}</p>', unsafe_allow_html=True)
                r2.markdown(f'<p class="order-label">Einsatz (CHF)</p><p class="order-value">{capital_per_trade:.2f}</p>', unsafe_allow_html=True)
                
                sl_base = price - (atr * 2) if final_dir == 'LONG' else price + (atr * 2)
                tp_v = price + (atr * 4) if final_dir == 'LONG' else price - (atr * 4)
                tsl_v = price - (atr * 1.5) if final_dir == 'LONG' else price + (atr * 1.5)
                
                st.info(f"Basis SL: ${sl_base:.2f} | TP: ${tp_v:.2f}")
                st.warning(f"Trailing SL Empfehlung: ${tsl_v:.2f}")
                st.markdown(f"**Strategischer Exit:** {ctx['exit']} Uhr")

        st.divider()
        st.subheader("🔗 Korrelation")
        corr_matrix = df[list(engine.assets.values())].corr()
        corr_matrix.columns = list(engine.assets.keys())
        corr_matrix.index = list(engine.assets.keys())
        st.dataframe(corr_matrix.style.background_gradient(cmap='RdYlGn', axis=None).format("{:.2f}"), use_container_width=True)
