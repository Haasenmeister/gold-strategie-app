import streamlit as st
import pandas as pd
import numpy as np
import os
import json
import requests
from datetime import datetime, timedelta
import pytz
import time
import yfinance as yf

st.set_page_config(page_title="Master Terminal Scalper v16.3", layout="wide")

TELEGRAM_TOKEN = "8500617608:AAHpWCJa24KU_GGq70ewQvb4s2sKj-DfDkI"
TELEGRAM_CHAT_ID = "8098807031"
TD_API_KEY = "06a5484d8d8d44c2a7bfac0a991761b9"

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

def send_telegram_msg(message):
    if TELEGRAM_TOKEN == "DEIN_TOKEN_HIER": return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try: requests.post(url, json=payload, timeout=3)
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
        self.td_map = {'GOLD': 'XAU/USD', 'SILBER': 'XAG/USD', 'WTI_ÖL': 'WTI/USD', 'KUPFER': 'XCU/USD', 'PLATIN': 'XPT/USD'}
        self.gmsi_tickers = {'USA': '^GSPC', 'EU': '^GDAXI', 'CHINA': '000001.SS', 'JAPAN': '^N225'}
        self.drivers = {'DXY': 'DX-Y.NYB', 'VIX': '^VIX'}

    def get_realtime_price(self, asset_name):
        symbol = self.td_map.get(asset_name)
        if symbol:
            try:
                url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={TD_API_KEY}"
                resp = requests.get(url, timeout=2).json()
                if 'price' in resp: return float(resp['price'])
            except: pass
        return None

    def get_td_candles(self, asset_name, interval="5min", outputsize=30):
        symbol = self.td_map.get(asset_name)
        if not symbol: return None
        try:
            url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={TD_API_KEY}"
            resp = requests.get(url, timeout=3)
            data = resp.json()
            if 'values' in data:
                df = pd.DataFrame(data['values'])
                df['close'] = pd.to_numeric(df['close'])
                df = df.iloc[::-1]
                return df['close']
            return None
        except: return None

    def get_market_status_info(self):
        now = datetime.now()
        weekday = now.weekday()
        if weekday >= 5: 
            return "🔴 WOCHENENDE", "Börse geschlossen"
        else:
            return "🟢 MARKT AKTIV (LIVE)", "Scalping möglich"

    def get_gmsi_data(self):
        tickers = list(self.gmsi_tickers.values()) + list(self.drivers.values())
        try:
            df = yf.download(tickers, period="5d", interval="1h", progress=False)['Close'].ffill().dropna()
            return df
        except: return pd.DataFrame()

    def calculate_gmsi(self, df, asset_name):
        if df.empty: return 0, 0, 0, 0
        c_w = 0.30 if asset_name in ['KUPFER', 'WTI_ÖL'] else 0.15
        j_w = 1.0 - 0.50 - 0.20 - c_w
        try:
            val = (df[self.gmsi_tickers['USA']] * 0.50 +
                   df[self.gmsi_tickers['EU']] * 0.20 +
                   df[self.gmsi_tickers['CHINA']] * c_w +
                   df[self.gmsi_tickers['JAPAN']] * j_w)
            
            dxy = df[self.drivers['DXY']]
            vix = df[self.drivers['VIX']]
            return val.iloc[-1], val.iloc[-2], dxy.iloc[-1], vix.iloc[-1]
        except: return 0, 0, 0, 0

    def calculate_rsi(self, series, period=9):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

state = load_state()
engine = TradingEngine()
tz_ch = pytz.timezone('Europe/Zurich')

st.title("🛡️ Master Terminal Scalper (Lvl 5.3)")

col_main, col_acc = st.columns([2, 1])

with col_acc:
    st.header("🏦 Depot & Monitoring")
    if st.button("🔔 TEST-NACHRICHT"):
        send_telegram_msg("🛡️ Scalper-Bot Test erfolgreich!")
        st.toast("Test gesendet!")
        
    bal = st.number_input("Kapital (CHF)", value=float(state['balance']))
    if bal != state['balance']:
        state['balance'] = bal
        save_state(state)
        
    st.metric("Gesamtprofit", f"{state['total_profit']:.2f} CHF")
    
    if state['active_trades']:
        st.subheader("⚡ Laufende Scalps")
        trades_to_close = []
        
        for asset, data in state['active_trades'].items():
            curr_p = engine.get_realtime_price(asset)
            if not curr_p: curr_p = data['entry']
            
            entry = data['entry']
            direction = data['dir']
            
            if direction == "KAUFEN":
                pnl_pct = (curr_p - entry) / entry
            else:
                pnl_pct = (entry - curr_p) / entry
            
            pnl_chf = state['balance'] * 20 * pnl_pct
            
            be_icon = ""
            if pnl_pct > 0.004 and not data.get('be_active'):
                data['be_active'] = True
                data['sl_price'] = entry
                save_state(state)
                send_telegram_msg(f"🛡️ <b>BREAK-EVEN: {asset}</b>\nStop-Loss auf Einstieg gezogen!")
            
            if data.get('be_active'): be_icon = "🛡️ BE"

            sl_hit = False
            if 'sl_price' in data:
                if direction == "KAUFEN" and curr_p < data['sl_price']: sl_hit = True
                if direction == "SHORTEN" and curr_p > data['sl_price']: sl_hit = True

            color = "#16a34a" if pnl_chf > 0 else "#dc2626"
            
            st.markdown(f"""
            <div class="active-trade-box">
                <b>{asset} {be_icon}</b> ({direction})<br>
                Einstieg: {entry:.2f} | Aktuell: {curr_p:.2f}<br>
                Profit: <span style="color:{color}"><b>{pnl_chf:.2f} CHF</b></span>
            </div>""", unsafe_allow_html=True)
            
            if sl_hit:
                st.error("STOP LOSS / BE GETROFFEN!")
                if st.button(f"Close {asset}", key=f"sl_{asset}"): trades_to_close.append((asset, pnl_chf))
            
            if st.button(f"Trade {asset} beenden", key=f"close_{asset}"):
                trades_to_close.append((asset, pnl_chf))
        
        for asset, pnl in trades_to_close:
            state['total_profit'] += pnl
            del state['active_trades'][asset]
            save_state(state)
            st.rerun()

with col_main:
    if st.button("🚀 LIVE-SCALPING STARTEN"):
        m_status, m_info = engine.get_market_status_info()
        st.markdown(f'<div class="live-status status-online"><div style="font-size: 1.2rem;">{m_status}</div><div style="font-size: 0.9rem;">{m_info}</div></div>', unsafe_allow_html=True)
        
        gmsi_df = engine.get_gmsi_data()
        
        for name in engine.td_map.keys():
            candles = engine.get_td_candles(name)
            
            if candles is None or len(candles) < 10:
                st.warning(f"{name}: Keine Daten geladen.")
                continue
                
            current_price = candles.iloc[-1]
            rsi = engine.calculate_rsi(candles).iloc[-1]
            g_now, g_prev, dxy_now, vix = engine.calculate_gmsi(gmsi_df, name)
            
            decision = "ABWARTEN"
            conf = 0
            
            if vix > 18: conf += 30
            if 25 <= rsi <= 35: conf += 30
            if 65 <= rsi <= 75: conf += 30
            
            if g_now < g_prev and rsi < 35:
                decision = "KAUFEN"
                conf += 30
            elif g_now > g_prev and rsi > 65:
                decision = "SHORTEN"
                conf += 30
            
            exp_label = f"{'✅ ' if decision != 'ABWARTEN' else '⚪ '}{name} | Preis: {current_price:.2f} | {decision} | RSI: {rsi:.1f}"
            
            with st.expander(exp_label, expanded=(decision != "ABWARTEN")):
                if decision != "ABWARTEN":
                    hebel = max(1, round((conf / 100) * 20))
                    t212_val = state['balance'] * hebel
                    tp = current_price * 1.006 if decision == "KAUFEN" else current_price * 0.994
                    sl = current_price * 0.996 if decision == "KAUFEN" else current_price * 1.004
                    
                    st.markdown(f"### {name} | <span class='glasklar'>{decision}</span>", unsafe_allow_html=True)
                    st.markdown(f"""<div style="background-color:#f8fafc;padding:15px;border-radius:10px;border:1px solid #e2e8f0;margin:10px 0;"><span style="color:#64748b;font-size:0.9rem;">HEBEL WERT (20x):</span><br><span class='t212-value'>{t212_val:.0f}</span></div>
                        <div style="display:flex;gap:10px;margin-bottom:20px;">
                        <div class="tp-box">TAKE PROFIT<br><b>{tp:.2f}</b></div>
                        <div class="sl-box">STOP LOSS<br><b>{sl:.2f}</b></div></div>""", unsafe_allow_html=True)
                    
                    last_sig = state['last_notified'].get(name, "")
                    if last_sig != decision:
                        msg = f"⚡ <b>SCALP: {name}</b>\nAktion: {decision}\nRSI: {rsi:.1f}\nPreis: {current_price:.2f}\nTP: {tp:.2f} | SL: {sl:.2f}"
                        send_telegram_msg(msg)
                        state['last_notified'][name] = decision
                        save_state(state)
                        st.toast(f"Signal an Telegram gesendet!")

                    if st.button(f"Trade für {name} aktivieren", key=f"start_{name}"):
                        state['active_trades'][name] = {
                            "entry": current_price, "dir": decision, "be_active": False,
                            "sl_price": sl, "t212_val": t212_val
                        }
                        save_state(state)
                        st.rerun()
                else:
                    st.write(f"RSI: {rsi:.1f} (Neutral) | VIX: {vix:.1f}")
            
            time.sleep(1.2)
