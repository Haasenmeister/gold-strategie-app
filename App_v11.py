import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime
import pytz

st.set_page_config(page_title="Multi-Commodity Pro Terminal Lvl 4", layout="wide")

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
        status, color, rec = "GESCHLOSSEN", "red", "Wochenende."
    elif current_hour == 23:
        status, color, rec = "PAUSE", "orange", "Täglicher Gap."
    else:
        status, color, rec = "AKTIV", "blue", "Handel aktiv."
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
        tickers = list(self.weights_std.keys()) + list(self.assets.values()) + ['^VIX', '^TNX']
        data = yf.download(tickers, period="60d", interval="1d", progress=False)['Close']
        data = data.ffill().dropna()
        for asset_name, ticker in self.assets.items():
            live_data = yf.download(ticker, period="1d", interval="1m", progress=False)['Close']
            if not live_data.empty:
                val = live_data.iloc[-1]
                if isinstance(val, pd.Series): val = val.iloc[0]
                data.loc[data.index[-1], ticker] = float(val)
        return data

    def calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def get_signal(self, name, current_gmsi, gmsi_sma, current_ratio, ratio_sma, vix, rsi, yields):
        vix_panic = vix > 25
        yields_rising = yields.diff().iloc[-1] > 0.02
        if name in ['GOLD', 'SILBER']:
            if yields_rising: return 'HOLD (Zins-Druck)'
            if (current_gmsi < gmsi_sma or vix_panic) and current_ratio > ratio_sma and rsi < 70: return 'LONG'
        elif name in ['WTI_ÖL', 'KUPFER']:
            if current_gmsi > gmsi_sma and current_ratio < ratio_sma and rsi < 70: return 'LONG'
        return 'HOLD'

    def get_noise_status(self, entry, price, atr):
        diff = abs(price - entry)
        if diff < (atr * 0.4): return "STABIL (Rauschen)", "blue"
        return ("POSITIV" if price > entry else "NEGATIV"), ("green" if price > entry else "red")

engine = TradingEngine()
history_df = load_history()
ctx = get_market_context()

if 'active_trades' not in st.session_state:
    st.session_state['active_trades'] = {}

st.title("💰 Multi-Commodity Pro Terminal Lvl 4")
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
        log_res = st.number_input("Gewinn/Verlust (CHF)", value=0.0)
        if st.form_submit_button("Manuell loggen"):
            history_df = save_to_history(history_df, {
                'Datum': datetime.now().strftime("%Y-%m-%d"),
                'Rohstoff': log_asset, 'Typ': 'EXIT', 'Einstieg': 0, 'Hebel': 0, 'Gewinn_CHF': log_res
            })
            st.rerun()

with col_main:
    if st.button("🚀 LEVEL 4 MARKT-ANALYSE STARTEN"):
        df = engine.fetch_data()
        vix_val = df['^VIX'].iloc[-1]
        yields_val = df['^TNX']
        results = []
        for name, ticker in engine.assets.items():
            w = engine.weights_eco if name in ['KUPFER', 'WTI_ÖL'] else engine.weights_std
            gmsi_series = (df['^GSPC'] * w['^GSPC']) + (df['^GDAXI'] * w['^GDAXI']) + (df['000001.SS'] * w['000001.SS']) + (df['^N225'] * w['^N225'])
            price_s = df[ticker]
            price, rsi = price_s.iloc[-1], engine.calculate_rsi(price_s).iloc[-1]
            atr = (price_s.rolling(2).max() - price_s.rolling(2).min()).rolling(14).mean().iloc[-1]
            sig = engine.get_signal(name, gmsi_series.iloc[-1], gmsi_series.rolling(20).mean().iloc[-1], price/gmsi_series.iloc[-1], (price_s/gmsi_series).rolling(20).mean().iloc[-1], vix_val, rsi, yields_val)
            results.append({'name': name, 'price': price, 'atr': atr, 'sig': sig, 'rsi': rsi, 'ratio': price/gmsi_series.iloc[-1], 'ratio_sma': (price_s/gmsi_series).rolling(20).mean().iloc[-1]})

        active_sigs = [r for r in results if r['sig'] != 'HOLD']
        cluster_metals = {'GOLD', 'SILBER', 'PLATIN'}
        metal_sigs = [r for r in active_sigs if r['name'] in cluster_metals]
        
        for res in results:
            name, price, sig, rsi, atr = res['name'], res['price'], res['sig'], res['rsi'], res['atr']
            is_active = name in st.session_state['active_trades']
            
            with st.expander(f"{'🔵 ' if is_active else '✅ ' if sig != 'HOLD' else '📊 '}{name}", expanded=(sig != 'HOLD' or is_active)):
                if is_active:
                    entry = st.session_state['active_trades'][name]
                    status, s_col = engine.get_noise_status(entry, price, atr)
                    st.markdown(f"**STATUS: :{s_col}[{status}]**")
                    if rsi > 70: st.error("ACHTUNG: RSI ÜBER 70! VERKAUF PRÜFEN!")
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Preis", f"${price:.2f}")
                m2.metric("Signal", sig)
                m3.metric("RSI", f"{rsi:.1f}")

                final_dir = sig if sig != 'HOLD' else ('LONG' if res['ratio'] > res['ratio_sma'] else 'SHORT')
                einsatz = current_bal / len(active_sigs) if active_sigs else current_bal
                if name in cluster_metals and len(metal_sigs) > 1:
                    einsatz = einsatz * 0.7
                    st.warning("Positionsmanagement: Einsatz reduziert wegen Korrelation.")
                
                tsl_val = price - (atr * 1.5) if final_dir == 'LONG' else price + (atr * 1.5)
                st.write(f"**Einsatz:** {einsatz:.2f} CHF | **T212 Trailing SL:** ${tsl_val:.2f}")

                if not is_active:
                    if st.button(f"KAUF BESTÄTIGEN: {name}", key=f"b_{name}"):
                        st.session_state['active_trades'][name] = price
                        st.rerun()
                else:
                    if st.button(f"VERKAUF LOGGEN: {name}", key=f"s_{name}"):
                        del st.session_state['active_trades'][name]
                        st.rerun()
