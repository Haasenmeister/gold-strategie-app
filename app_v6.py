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
    .stApp { background-color: #FFFFFF; }
    .order-label { color: #6B7280; font-size: 0.85rem; text-transform: uppercase; margin-bottom: 2px; font-weight: 600; }
    .order-value { color: #111827; font-size: 1.25rem; font-weight: bold; margin-bottom: 10px; }
    .stMetric { background-color: #F3F4F6; border: 1px solid #E5E7EB; border-radius: 8px; padding: 10px; }
    .ready-card { background-color: #ECFDF5; border: 2px solid #10B981; border-radius: 10px; padding: 15px; margin-bottom: 10px; }
    .stButton>button { background-color: #FFD700 !important; color: #000000 !important; border-radius: 8px; font-weight: bold; border: none; }
    h1, h2, h3, p { color: #111827 !important; }
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
        self.weights = {'^GSPC': 0.50, '^GDAXI': 0.20, '000001.SS': 0.15, '^N225': 0.15}
        self.assets = {'GOLD': 'GC=F', 'SILBER': 'SI=F', 'WTI_ÖL': 'CL=F', 'KUPFER': 'HG=F', 'PLATIN': 'PL=F'}

    def fetch_data(self):
        tickers = list(self.weights.keys()) + list(self.assets.values()) + ['^VIX']
        data = yf.download(tickers, period="60d", interval="1d", progress=False)['Close']
        return data.ffill().dropna()

    def get_signal(self, name, current_gmsi, gmsi_sma, current_ratio, ratio_sma, current_vix):
        vix_panic = current_vix > 25
        if name in ['GOLD', 'SILBER', 'PLATIN']:
            if (current_gmsi < gmsi_sma or vix_panic) and current_ratio > ratio_sma: return 'LONG'
            if current_gmsi > gmsi_sma and current_ratio < ratio_sma: return 'SHORT'
        elif name in ['WTI_ÖL', 'KUPFER']:
            if current_gmsi > gmsi_sma and current_ratio < ratio_sma: return 'LONG'
            if current_gmsi < gmsi_sma and current_ratio > ratio_sma: return 'SHORT'
        return 'HOLD'

engine = TradingEngine()
history_df = load_history()
ctx = get_market_context()

st.title("💰 Multi-Commodity Pro Terminal")
st.markdown(f"**Schweizer Zeit:** {ctx['time']} | **Status:** :{ctx['color']}[{ctx['status']}]")
st.info(f"**Empfehlung:** {ctx['rec']}")

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
    if st.button("🔍 ALLE ROHSTOFFE ANALYSIEREN", use_container_width=True):
        df = engine.fetch_data()
        vix_val = df['^VIX'].iloc[-1]
        gmsi = (df['^GSPC'] * 0.50) + (df['^GDAXI'] * 0.20) + (df['000001.SS'] * 0.15) + (df['^N225'] * 0.15)
        gmsi_sma = gmsi.rolling(20).mean().iloc[-1]
        
        results = []
        for name, ticker in engine.assets.items():
            price_s = df[ticker]
            price = price_s.iloc[-1]
            ratio = price / gmsi.iloc[-1]
            ratio_sma = (price_s / gmsi).rolling(20).mean().iloc[-1]
            atr = (price_s.rolling(2).max() - price_s.rolling(2).min()).rolling(14).mean().iloc[-1]
            sig = engine.get_signal(name, gmsi.iloc[-1], gmsi_sma, ratio, ratio_sma, vix_val)
            results.append({'name': name, 'price': price, 'ratio': ratio, 'ratio_sma': ratio_sma, 'atr': atr, 'sig': sig})
        
        active_signals = [r for r in results if r['sig'] != 'HOLD']
        num_active = len(active_signals)
        capital_per_trade = current_bal / num_active if num_active > 0 else current_bal

        if num_active > 0:
            st.success(f"🚀 **READY TO INVEST:** {num_active} Signal(e) gefunden. Kapital wurde aufgeteilt: **{capital_per_trade:.2f} CHF pro Trade.**")
        else:
            st.warning("Keine klaren Signale. Zeige Tendenz-Vorschau basierend auf Ratio.")

        for res in results:
            name, price, atr, sig = res['name'], res['price'], res['atr'], res['sig']
            vola = (atr / price) * 100
            lev = 7 if vola < 0.8 else 5 if vola < 1.5 else 2 if vola < 2.5 else 1
            if capital_per_trade > 25000: lev = min(lev, 3)
            
            final_dir = sig if sig != 'HOLD' else ('LONG' if res['ratio'] > res['ratio_sma'] else 'SHORT')
            is_ready = sig != 'HOLD'
            
            with st.expander(f"{'✅ ' if is_ready else '📊 '}{name} ANALYSE", expanded=is_ready):
                if is_ready:
                    st.markdown(f'<div style="color: #065F46; font-weight: bold; margin-bottom: 10px;">➔ DIESER ROHSTOFF IST BEREIT ZUM INVESTIEREN</div>', unsafe_allow_html=True)
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Preis", f"${price:.2f}")
                m2.metric("Hebel", f"{lev}x")
                m3.metric("Signal", sig)
                m4.metric("Kapital-Anteil", f"{capital_per_trade:.2f} CHF")

                st.markdown(f"**📲 Trading 212 Cockpit ({name})**")
                r1_1, r1_2, r1_3 = st.columns(3)
                r1_1.markdown(f'<p class="order-label">Richtung</p><p class="order-value" style="color:{"#10B981" if final_dir == "LONG" else "#EF4444"}">{final_dir}</p>', unsafe_allow_html=True)
                r1_2.markdown(f'<p class="order-label">Wert (CHF)</p><p class="order-value">{capital_per_trade * lev:.2f}</p>', unsafe_allow_html=True)
                r1_3.markdown(f'<p class="order-label">Typ</p><p class="order-value">Markt / Limit</p>', unsafe_allow_html=True)

                r2_1, r2_2, r2_3 = st.columns(3)
                sl_v = price - (atr * 2) if final_dir == 'LONG' else price + (atr * 2)
                tp_v = price + (atr * 4) if final_dir == 'LONG' else price - (atr * 4)
                r2_1.markdown(f'<p class="order-label">Stop-Loss</p><p class="order-value" style="color:#EF4444">${sl_v:.2f}</p>', unsafe_allow_html=True)
                r2_2.markdown(f'<p class="order-label">Take-Profit</p><p class="order-value" style="color:#10B981">${tp_v:.2f}</p>', unsafe_allow_html=True)
                r2_3.markdown(f'<p class="order-label">Limit/Stop</p><p class="order-value">${price:.2f}</p>', unsafe_allow_html=True)

                st.warning(f"🕒 **Strategischer Exit:** Manuell schliessen um **{ctx['exit']} Uhr**, falls TP nicht erreicht.")

    st.divider()
    if not history_df.empty:
        st.subheader("📜 Historie")
        st.dataframe(history_df.sort_index(ascending=False), use_container_width=True)
