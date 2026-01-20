import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
import json
import requests
from datetime import datetime, timedelta
import pytz
import time

st.set_page_config(page_title="Master Terminal Lvl 5.2 Ultra", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #ffffff; color: #1e293b; }
    .stMetric { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; }
    .instruction-card { background-color: #ffffff; border: 1px solid #e2e8f0; border-left: 6px solid #2563eb; padding: 25px; border-radius: 8px; margin-bottom: 25px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
    .sniper-box { background-color: #fef2f2; border: 2px solid #ef4444; border-radius: 12px; padding: 20px; text-align: center; color: #b91c1c; font-weight: 800; animation: pulse 2s infinite; margin-bottom: 15px; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }
    .t212-value { color: #2563eb; font-size: 2.8rem; font-weight: 900; display: block; margin: 10px 0; }
    .stButton>button { background-color: #2563eb !important; color: white !important; font-weight: bold; width: 100%; height: 55px; border-radius: 12px; border: none; font-size: 1.1rem; }
    .glasklar { font-size: 1.6rem; font-weight: 900; text-transform: uppercase; color: #1e293b; border-bottom: 3px solid #2563eb; }
    .active-trade-box { background-color: #f0fdf4; border: 1px solid #16a34a; border-radius: 10px; padding: 15px; margin-bottom: 15px; }
    .exit-signal { background-color: #fff1f2; border: 2px solid #be123c; color: #be123c; padding: 15px; border-radius: 10px; font-weight: bold; text-align: center; animation: pulse 1s infinite; }
    .live-status { padding: 15px; border-radius: 10px; font-weight: bold; text-align: center; margin-bottom: 20px; border: 1px solid #e2e8f0; }
    .status-online { background-color: #dcfce7; color: #166534; border-color: #16a34a; }
    .status-offline { background-color: #fee2e2; color: #991b1b; border-color: #ef4444; }
    .tp-box { background-color: #f0fdf4; padding: 10px; border-radius: 8px; border: 1px solid #16a34a; flex: 1; text-align: center; }
    .sl-box { background-color: #fff1f2; padding: 10px; border-radius: 8px; border: 1px solid #be123c; flex: 1; text-align: center; }
    </style>
""", unsafe_allow_html=True)

TELEGRAM_TOKEN = "8500617608:AAHpWCJa24KU_GGq70ewQvb4s2sKj-DfDkI"
TELEGRAM_CHAT_ID = "8098807031"

def send_telegram_msg(message):
    if TELEGRAM_TOKEN == "DEIN_TOKEN_HIER": return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try: requests.post(url, json=payload, timeout=5)
    except: pass

def load_state():
    default_state = {"balance": 5000.0, "total_profit": 0.0, "active_trades": {}, "last_notified": {}, "last_test_sent": ""}
    if os.path.exists('account_state.json'):
        try:
            with open('account_state.json', 'r') as f:
                data = json.load(f)
                for key in default_state:
                    if key not in data: data[key] = default_state[key]
                return data
        except: return default_state
    return default_state

def save_state(data):
    with open('account_state.json', 'w') as f:
        json.dump(data, f)

class TradingEngine:
    def __init__(self):
        self.assets = {'GOLD': 'GC=F', 'SILBER': 'SI=F', 'WTI_ÖL': 'CL=F', 'KUPFER': 'HG=F', 'PLATIN': 'PL=F'}
        self.gmsi_tickers = {'USA': '^GSPC', 'EU': '^GDAXI', 'CHINA': '000001.SS', 'JAPAN': '^N225'}
        self.drivers = {'DXY': 'DX-Y.NYB', 'Yields': '^TNX', 'VIX': '^VIX'}

    def fetch_data(self):
        all_t = list(self.assets.values()) + list(self.gmsi_tickers.values()) + list(self.drivers.values())
        return yf.download(all_t, period="5d", interval="1h", progress=False)['Close'].ffill().dropna()

    def get_gmsi(self, df, asset_name):
        c_w = 0.30 if asset_name in ['KUPFER', 'WTI_ÖL'] else 0.15
        j_w = 1.0 - 0.50 - 0.20 - c_w
        val = (df[self.gmsi_tickers['USA']] * 0.50 +
               df[self.gmsi_tickers['EU']] * 0.20 +
               df[self.gmsi_tickers['CHINA']] * c_w +
               df[self.gmsi_tickers['JAPAN']] * j_w)
        return val

    def get_market_status_info(self):
        tz_ny = pytz.timezone('America/New_York')
        now_ny = datetime.now(tz_ny)
        weekday = now_ny.weekday()
        day_month = (now_ny.month, now_ny.day)
        holidays = [(1, 1), (1, 20), (2, 17), (4, 18), (5, 26), (6, 19), (7, 4), (9, 1), (11, 27), (12, 25)]
        is_holiday = day_month in holidays
        open_time = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
        close_time = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
        if weekday >= 5 or is_holiday:
            return "🔴 BÖRSE GESCHLOSSEN", "Nächste Eröffnung: Montag 15:30 MEZ"
        if now_ny < open_time:
            return "🟡 MARKT NOCH GESCHLOSSEN", "Öffnet heute um 15:30 MEZ"
        elif now_ny > close_time:
            return "🔴 MARKT FÜR HEUTE ZU", "Öffnet morgen um 15:30 MEZ"
        else:
            return "🟢 MARKT AKTIV (LIVE)", "Schließt heute um 22:00 MEZ"

    def check_live_market(self, df):
        last_ts = df.index[-1]
        now_utc = datetime.now(pytz.utc)
        diff = (now_utc - last_ts.to_pydatetime().replace(tzinfo=pytz.utc)).total_seconds() / 60
        return diff < 90

    def calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

state = load_state()
engine = TradingEngine()
tz_ch = pytz.timezone('Europe/Zurich')
now_ch = datetime.now(tz_ch)

if now_ch.hour == 0 and now_ch.minute == 28:
    today_str = now_ch.strftime("%Y-%m-%d")
    if state.get("last_test_sent") != today_str:
        send_telegram_msg("⏰ Geplanter System-Test um 00:20 Uhr erfolgreich! Das Programm ist online und sendebereit.")
        state["last_test_sent"] = today_str
        save_state(state)

if "last_auto_check" not in st.session_state:
    st.session_state.last_auto_check = datetime.now() - timedelta(minutes=10)

def perform_analysis():
    df = engine.fetch_data()
    dxy_now, dxy_prev = df[engine.drivers['DXY']].iloc[-1], df[engine.drivers['DXY']].iloc[-2]
    vix = df[engine.drivers['VIX']].iloc[-1]
    
    for name, ticker in engine.assets.items():
        p_s = df[ticker]
        p_now, p_prev = p_s.iloc[-1], p_s.iloc[-2]
        g_s = engine.get_gmsi(df, name)
        g_now, g_prev = g_s.iloc[-1], g_s.iloc[-2]
        r_s = p_s / g_s
        r_now, r_sma = r_s.iloc[-1], r_s.rolling(20).mean().iloc[-1]
        rsi = engine.calculate_rsi(p_s).iloc[-1]
        atr = (p_s.rolling(2).max() - p_s.rolling(2).min()).rolling(14).mean().iloc[-1]
        vola = (atr / p_now) * 100
        
        conf = 0
        if vola < 0.45: conf += 30
        if dxy_now < dxy_prev: conf += 20
        if 40 <= rsi <= 60: conf += 20
        if vix > 18: conf += 30
        conf = min(int(conf), 100)
        
        decision = "ABWARTEN"
        krisen_muster = g_now < g_prev and p_now >= p_prev
        inflations_muster = g_now > (g_prev * 1.001) and p_now > (p_prev * 1.001)
        
        if conf >= 60:
            if (krisen_muster or inflations_muster) and r_now > r_sma: decision = "KAUFEN"
            elif r_now < r_sma: decision = "SHORTEN"
        
        if decision != "ABWARTEN":
            if state['last_notified'].get(name) != decision:
                t212_val = state['balance'] * max(1, round((conf / 100) * 20))
                tp_dyn = 0.01 + (conf/100*0.006)
                sl_dyn = 0.01 - (conf/100*0.005)
                tp_p = p_now * (1+tp_dyn) if decision == "KAUFEN" else p_now * (1-tp_dyn)
                sl_p = p_now * (1-sl_dyn) if decision == "KAUFEN" else p_now * (1+sl_dyn)
                
                msg = f"🚀 <b>SIGNAL: {name}</b>\nAktion: {decision}\nSicherheit: {conf}%\nWert: {t212_val:.0f} CHF\nTP: {tp_p:.2f}\nSL: {sl_p:.2f}"
                send_telegram_msg(msg)
                state['last_notified'][name] = decision
                save_state(state)
    return df

if datetime.now() - st.session_state.last_auto_check > timedelta(minutes=5):
    st.session_state.last_auto_check = datetime.now()
    perform_analysis()

exit_dt = datetime.combine(now_ch.date(), datetime.strptime("22:45", "%H:%M").time()).replace(tzinfo=tz_ch)
if now_ch > exit_dt: exit_dt += timedelta(days=1)
countdown = exit_dt - now_ch

st.title("🛡️ Master Terminal Lvl 5.2 - Ultra")

col_main, col_acc = st.columns([2, 1])

with col_acc:
    st.header("🏦 Depot & Monitoring")
    if st.button("🔔 TEST-NACHRICHT JETZT SENDEN"):
        send_telegram_msg("🛡️ Manueller Verbindungstest erfolgreich!")
        st.toast("Test gesendet!")
        
    bal = st.number_input("Kapital (CHF)", value=float(state['balance']))
    if bal != state['balance']:
        state['balance'] = bal
        save_state(state)
    st.metric("Gesamtprofit", f"{state['total_profit']:.2f} CHF")
    st.write(f"⏱ Zeit bis Exit: {str(countdown).split('.')[0]}")
    
    if state['active_trades']:
        st.subheader("🟢 Laufende Positionen")
        df_live = engine.fetch_data()
        for asset, data in list(state['active_trades'].items()):
            current_p = df_live[engine.assets[asset]].iloc[-1]
            entry_p, direction, t212_val = data['entry'], data['dir'], data['t212_val']
            pnl_pct = ((current_p - entry_p) / entry_p) * 100 if direction == "KAUFEN" else ((entry_p - current_p) / entry_p) * 100
            pnl_chf = (t212_val * pnl_pct) / 100
            st.markdown(f"""<div class="active-trade-box"><b>{asset} ({direction})</b><br>Einstieg: {entry_p:.2f} | Aktuell: {current_p:.2f}<br>Profit: <span style="color:{'#16a34a' if pnl_chf > 0 else '#dc2626'}"><b>{pnl_chf:.2f} CHF ({pnl_pct:.2f}%)</b></span></div>""", unsafe_allow_html=True)
            if pnl_pct > 1.5 or pnl_pct < -0.8 or countdown < timedelta(minutes=10):
                st.markdown('<div class="exit-signal">⚠️ EXIT-SIGNAL: JETZT SCHLIESSEN!</div>', unsafe_allow_html=True)
            if st.button(f"Trade {asset} beenden", key=f"close_{asset}"):
                state['total_profit'] += pnl_chf
                del state['active_trades'][asset]
                save_state(state)
                st.rerun()

with col_main:
    if st.button("🚀 LIVE-MARKT ANALYSIEREN"):
        df = perform_analysis()
        m_status, m_info = engine.get_market_status_info()
        is_live_data = engine.check_live_market(df)
        status_class = "status-online" if is_live_data and "AKTIV" in m_status else "status-offline"
        st.markdown(f'<div class="live-status {status_class}"><div style="font-size: 1.2rem;">{m_status}</div><div style="font-size: 0.9rem;">{m_info}</div></div>', unsafe_allow_html=True)
        
        vix = df[engine.drivers['VIX']].iloc[-1]
        dxy_now, dxy_prev = df[engine.drivers['DXY']].iloc[-1], df[engine.drivers['DXY']].iloc[-2]
        
        for name, ticker in engine.assets.items():
            p_s = df[ticker]
            p_now = p_s.iloc[-1]
            g_s = engine.get_gmsi(df, name)
            g_now, g_prev = g_s.iloc[-1], g_s.iloc[-2]
            r_s = p_s / g_s
            r_now, r_sma = r_s.iloc[-1], r_s.rolling(20).mean().iloc[-1]
            rsi = engine.calculate_rsi(p_s).iloc[-1]
            atr = (p_s.rolling(2).max() - p_s.rolling(2).min()).rolling(14).mean().iloc[-1]
            vola = (atr / p_now) * 100
            
            conf = 0
            if vola < 0.45: conf += 30
            if dxy_now < dxy_prev: conf += 20
            if 40 <= rsi <= 60: conf += 20
            if vix > 18: conf += 30
            conf = min(int(conf), 100)
            
            decision = "ABWARTEN"
            krisen_muster = g_now < g_prev and p_now >= p_s.iloc[-2]
            inflations_muster = g_now > (g_prev * 1.001) and p_now > (p_s.iloc[-2] * 1.001)
            if conf >= 60:
                if (krisen_muster or inflations_muster) and r_now > r_sma: decision = "KAUFEN"
                elif r_now < r_sma: decision = "SHORTEN"
            
            exp_label = f"{'✅ ' if decision != 'ABWARTEN' else '⚪ '}{name} | Preis: {p_now:.2f} | {decision} | Sicherheit: {conf}%"
            with st.expander(exp_label, expanded=(decision != "ABWARTEN")):
                if decision != "ABWARTEN":
                    hebel = max(1, round((conf / 100) * 20))
                    t212_val = state['balance'] * hebel
                    tp_dyn, sl_dyn = 0.01 + (conf/100*0.006), 0.01 - (conf/100*0.005)
                    tp_p = p_now * (1+tp_dyn) if decision == "KAUFEN" else p_now * (1-tp_dyn)
                    sl_p = p_now * (1-sl_dyn) if decision == "KAUFEN" else p_now * (1+sl_dyn)
                    
                    st.markdown('<div class="instruction-card">', unsafe_allow_html=True)
                    if hebel >= 18: st.markdown('<div class="sniper-box">🎯 MAXIMUM SNIPER-HEBEL AKTIVIERT (20x)</div>', unsafe_allow_html=True)
                    st.markdown(f"### {name} | <span class='glasklar'>{decision}</span>", unsafe_allow_html=True)
                    st.markdown(f"""<div style="background-color:#f8fafc;padding:15px;border-radius:10px;border:1px solid #e2e8f0;margin:10px 0;"><span style="color:#64748b;font-size:0.9rem;">T212 EINGABEWERT:</span><br><span class='t212-value'>{t212_val:.0f}</span></div>
                        <div style="display:flex;gap:10px;margin-bottom:20px;"><div class="tp-box"><span style="color:#166534;font-size:0.8rem;">TAKE PROFIT</span><br><b style="font-size:1.2rem;">{tp_p:.2f}</b></div><div class="sl-box"><span style="color:#991b1b;font-size:0.8rem;">STOP LOSS</span><br><b style="font-size:1.2rem;">{sl_p:.2f}</b></div></div>""", unsafe_allow_html=True)
                    entry_in = st.number_input(f"Echter Einstieg ({name})", value=float(p_now), key=f"in_{name}")
                    if st.button(f"Trade für {name} aktivieren", key=f"start_{name}"):
                        state['active_trades'][name] = {"entry": entry_in, "dir": decision, "t212_val": t212_val}
                        save_state(state)
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                else: st.write(f"Vola: {vola:.2f}% | RSI: {rsi:.1f} | DXY: {'Sinkt' if dxy_now < dxy_prev else 'Steigend'}")
