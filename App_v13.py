import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime
import pytz

st.set_page_config(page_title="Multi-Commodity Ultra Terminal Lvl 4.1 FIX", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0f172a; color: #f8fafc; }
    .stMetric { background-color: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 15px; }
    .stButton>button { background-color: #3b82f6 !important; color: white !important; border-radius: 5px; width: 100%; font-weight: bold; border: none; }
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
    weekday = now.weekday()
    exit_time = "22:30" if weekday == 4 else "22:45"
    status = "AKTIV" if now.hour < 23 else "PAUSE"
    return {"time": now.strftime("%H:%M:%S"), "status": status, "exit": exit_time}

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
            live = yf.download(ticker, period="1d", interval="1m", progress=False)['Close']
            if not live.empty:
                val = live.iloc[-1]
                data.loc[data.index[-1], ticker] = float(val.iloc[0]) if isinstance(val, pd.Series) else float(val)
        return data

    def check_smart_entry(self, ticker, direction):
        h1_data = yf.download(ticker, period="2d", interval="1h", progress=False)['Close']
        if h1_data.empty or len(h1_data) < 2: return True
        last_price = float(h1_data.iloc[-1].iloc[0]) if isinstance(h1_data.iloc[-1], pd.Series) else float(h1_data.iloc[-1])
        prev_price = float(h1_data.iloc[-2].iloc[0]) if isinstance(h1_data.iloc[-2], pd.Series) else float(h1_data.iloc[-2])
        if "LONG" in direction:
            return last_price <= prev_price
        elif "SHORT" in direction:
            return last_price >= prev_price
        return True

    def calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def get_signal(self, name, current_gmsi, gmsi_sma, current_ratio, ratio_sma, vix, rsi, yields):
        yields_rising = yields.diff().iloc[-1] > 0.02
        pattern = "Neutral"
        if current_gmsi < gmsi_sma and current_ratio > ratio_sma: pattern = "KRISEN-MUSTER"
        elif current_gmsi > gmsi_sma and current_ratio > ratio_sma and rsi > 50: pattern = "INFLATIONS-MUSTER"
        
        if name in ['GOLD', 'SILBER', 'PLATIN']:
            if (current_gmsi < gmsi_sma or vix > 25) and current_ratio > ratio_sma and rsi < 70:
                return ('LONG (Zins-Warnung)' if yields_rising else 'LONG'), pattern
            if current_gmsi > gmsi_sma and current_ratio < ratio_sma and rsi > 30:
                return 'SHORT', pattern
        elif name in ['WTI_ÖL', 'KUPFER']:
            if current_gmsi > gmsi_sma and current_ratio < ratio_sma and rsi < 70:
                return 'LONG', pattern
            if current_gmsi < gmsi_sma and current_ratio > ratio_sma and rsi > 30:
                return 'SHORT', pattern
        return 'HOLD', pattern

    def get_noise_status(self, entry, price, atr, direction):
        diff = price - entry if "LONG" in direction else entry - price
        if abs(diff) < (atr * 0.4): return "STABIL (Rauschen)", "blue"
        return ("POSITIV" if diff > 0 else "NEGATIV"), ("green" if diff > 0 else "red")

engine = TradingEngine()
history_df = load_history()
ctx = get_market_context()

if 'active_trades' not in st.session_state: st.session_state['active_trades'] = {}
if 'analysis_results' not in st.session_state: st.session_state['analysis_results'] = None

st.title("💰 Multi-Commodity Ultra Terminal Lvl 4.1 FIX")
st.markdown(f"**Zeit:** {ctx['time']} | **Status:** {ctx['status']}")

col_main, col_depot = st.columns([2, 1])

with col_depot:
    st.header("🏦 Depot & Tracking")
    start_kap = st.number_input("Startkapital (CHF)", value=5000.0)
    total_p = history_df['Gewinn_CHF'].sum() if not history_df.empty else 0.0
    st.metric("Kontostand", f"{(start_kap + total_p):.2f} CHF", delta=f"{total_p:.2f} CHF")
    st.divider()
    if st.session_state['active_trades']:
        for t_name, t_info in list(st.session_state['active_trades'].items()):
            st.info(f"Aktiv: {t_name} ({t_info['dir']}) ab ${t_info['entry']:.2f}")
            if st.button(f"Löschen {t_name}", key=f"rm_{t_name}"):
                del st.session_state['active_trades'][t_name]
                st.rerun()

with col_main:
    if st.button("🚀 LEVEL 4 VOLL-ANALYSE STARTEN"):
        df = engine.fetch_data()
        vix_val, yields_val = df['^VIX'].iloc[-1], df['^TNX']
        results = []
        for name, ticker in engine.assets.items():
            if vix_val > 25: w = engine.weights_crisis
            elif name in ['KUPFER', 'WTI_ÖL']: w = engine.weights_eco
            else: w = engine.weights_std
            
            gmsi_series = (df['^GSPC'] * w['^GSPC']) + (df['^GDAXI'] * w['^GDAXI']) + (df['000001.SS'] * w['000001.SS']) + (df['^N225'] * w['^N225'])
            gmsi_val, gmsi_sma = gmsi_series.iloc[-1], gmsi_series.rolling(20).mean().iloc[-1]
            price_s = df[ticker]
            price, rsi = price_s.iloc[-1], engine.calculate_rsi(price_s).iloc[-1]
            atr = (price_s.rolling(2).max() - price_s.rolling(2).min()).rolling(14).mean().iloc[-1]
            sig, pat = engine.get_signal(name, gmsi_val, gmsi_sma, price/gmsi_val, (price_s/gmsi_series).rolling(20).mean().iloc[-1], vix_val, rsi, yields_val)
            smart = engine.check_smart_entry(ticker, sig)
            results.append({'name': name, 'price': price, 'atr': atr, 'sig': sig, 'rsi': rsi, 'ratio': price/gmsi_val, 'ratio_sma': (price_s/gmsi_series).rolling(20).mean().iloc[-1], 'pattern': pat, 'smart': smart})
        st.session_state['analysis_results'] = results

    if st.session_state['analysis_results']:
        res_list = st.session_state['analysis_results']
        active_sigs = [r for r in res_list if "LONG" in r['sig'] or "SHORT" in r['sig']]
        metal_sigs = [r for r in active_sigs if r['name'] in {'GOLD', 'SILBER', 'PLATIN'}]
        
        for res in res_list:
            name, price, sig, rsi, atr, pat, smart = res['name'], res['price'], res['sig'], res['rsi'], res['atr'], res['pattern'], bool(res['smart'])
            is_active = name in st.session_state['active_trades']
            final_dir = sig if "HOLD" not in sig else ("LONG" if res['ratio'] > res['ratio_sma'] else "SHORT")
            clean_dir = "LONG" if "LONG" in final_dir else "SHORT"

            with st.expander(f"{'🔵 ' if is_active else '✅ ' if 'HOLD' not in sig else '📊 '}{name} | {pat}", expanded=(sig != 'HOLD' or is_active)):
                if is_active:
                    t_info = st.session_state['active_trades'][name]
                    status, s_col = engine.get_noise_status(t_info['entry'], price, atr, t_info['dir'])
                    st.markdown(f"**STATUS: :{s_col}[{status}]**")
                
                decision_sig = "LONG" if "LONG" in sig else "SHORT" if "SHORT" in sig else "ABWARTEN"
                decision = f"GLASKLARE ANTWORT: {decision_sig}" if (decision_sig != "ABWARTEN" and smart) else f"GLASKLARE ANTWORT: {decision_sig} (WARTE SMART ENTRY)" if decision_sig != "ABWARTEN" else "GLASKLARE ANTWORT: ABWARTEN"
                st.subheader(decision)

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Preis", f"${price:.2f}")
                m2.metric("Signal", sig)
                m3.metric("RSI", f"{rsi:.1f}")
                vola_p = (atr / price) * 100
                lev = 7 if vola_p < 0.8 else 5 if vola_p < 1.5 else 2 if vola_p < 2.5 else 1
                m4.metric("Empf. Hebel", f"{lev}x")

                st.markdown("---")
                einsatz = start_kap / len(active_sigs) if active_sigs else start_kap
                if name in {'GOLD', 'SILBER', 'PLATIN'} and len(metal_sigs) > 1: einsatz *= 0.7
                
                sl, tp, tsl = (price - atr*2, price + atr*4, price - atr*1.5) if clean_dir == "LONG" else (price + atr*2, price - atr*4, price + atr*1.5)

                t1, t2, t3 = st.columns(3)
                t1.markdown(f'<p class="order-label">Richtung</p><p class="order-value">{clean_dir}</p>', unsafe_allow_html=True)
                t2.markdown(f'<p class="order-label">Einsatz (CHF)</p><p class="order-value">{einsatz:.2f}</p>', unsafe_allow_html=True)
                t3.markdown(f'<p class="order-label">T212 Hebel</p><p class="order-value">{lev}x</p>', unsafe_allow_html=True)

                st.info(f"Basis SL: ${sl:.2f} | TP: ${tp:.2f}")
                st.warning(f"T212 Trailing Stop: ${tsl:.2f}")

                if not is_active:
                    if st.button(f"BESTÄTIGE {clean_dir}: {name}", key=f"b_{name}"):
                        st.session_state['active_trades'][name] = {'entry': price, 'dir': clean_dir}
                        st.rerun()
                else:
                    if st.button(f"CLOSE {name} & LOG", key=f"s_{name}"):
                        del st.session_state['active_trades'][name]
                        st.rerun()
