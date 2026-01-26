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

# --- KONFIGURATION ---
st.set_page_config(page_title="Master Terminal Scalper v16.2", layout="wide")
TELEGRAM_TOKEN = "8500617608:AAHpWCJa24KU_GGq70ewQvb4s2sKj-DfDkI"
TELEGRAM_CHAT_ID = "8098807031"
TD_API_KEY = "06a5484d8d8d44c2a7bfac0a991761b9"

# --- CSS STYLING (Original übernommen & angepasst) ---
st.markdown("""
    <style>
    .stApp { background-color: #0f172a; color: #f8fafc; }
    .stMetric { background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 15px; }
    .active-trade-box { background-color: #111827; border: 1px solid #3b82f6; border-radius: 8px; padding: 15px; margin-bottom: 10px; }
    .sniper-box { background-color: #450a0a; border: 1px solid #ef4444; border-radius: 8px; padding: 15px; text-align: center; color: #fca5a5; font-weight: 800; animation: pulse 1.5s infinite; margin-bottom: 15px; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.6; } 100% { opacity: 1; } }
    .t212-value { color: #60a5fa; font-size: 2.2rem; font-weight: 800; display: block; margin: 8px 0; }
    .stButton>button { background-color: #2563eb !important; color: white !important; font-weight: bold; width: 100%; height: 50px; border-radius: 8px; border: none; font-size: 1.1rem; }
    .glasklar { font-size: 1.4rem; font-weight: 800; text-transform: uppercase; color: #f8fafc; border-bottom: 2px solid #3b82f6; }
    .live-status { padding: 12px; border-radius: 8px; font-weight: bold; text-align: center; margin-bottom: 15px; border: 1px solid #334155; }
    .status-online { background-color: #064e3b; color: #6ee7b7; border-color: #059669; }
    .status-offline { background-color: #450a0a; color: #fca5a5; border-color: #b91c1c; }
    .tp-box { background-color: #064e3b; padding: 8px; border-radius: 6px; border: 1px solid #059669; flex: 1; text-align: center; }
    .sl-box { background-color: #450a0a; padding: 8px; border-radius: 6px; border: 1px solid #7f1d1d; flex: 1; text-align: center; }
    </style>
""", unsafe_allow_html=True)

# --- FUNKTIONEN ---

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
        # Assets & Mapping
        self.td_map = {'GOLD': 'XAU/USD', 'SILBER': 'XAG/USD', 'WTI_ÖL': 'WTI/USD', 'KUPFER': 'XCU/USD', 'PLATIN': 'XPT/USD'}
        self.gmsi_tickers = {'USA': '^GSPC', 'EU': '^GDAXI', 'CHINA': '000001.SS', 'JAPAN': '^N225'}
        self.drivers = {'DXY': 'DX-Y.NYB', 'VIX': '^VIX'}

    def get_realtime_price(self, asset_name):
        # 1. Versuch: Twelve Data (Schnell)
        symbol = self.td_map.get(asset_name)
        if symbol:
            try:
                url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={TD_API_KEY}"
                resp = requests.get(url, timeout=2).json()
                if 'price' in resp: return float(resp['price'])
            except: pass
        # 2. Versuch: Yahoo Fallback
        return None

    def get_td_candles(self, asset_name, interval="5min", outputsize=30):
        # Holt schnelle Kerzen für RSI
        symbol = self.td_map.get(asset_name)
        if not symbol: return None
        try:
            url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={TD_API_KEY}"
            resp = requests.get(url, timeout=3)
            data = resp.json()
            if 'values' in data:
                df = pd.DataFrame(data['values'])
                df['close'] = pd.to_numeric(df['close'])
                df = df.iloc[::-1] # Umdrehen, damit aktuellstes unten ist
                return df['close']
            return None
        except: return None

    def get_market_status_info(self):
        # Original Markt-Check wieder eingebaut
        tz_ny = pytz.timezone('America/New_York')
        now_ny = datetime.now(tz_ny)
        weekday = now_ny.weekday()
        # Vereinfachte Feiertage (Sample)
        open_time = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
        close_time = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
        
        if weekday >= 5: # Wochenende
            return "🔴 BÖRSE ZU (Wochenende)", "Achtung: Geringe Liquidität möglich"
        if now_ny < open_time or now_ny > close_time:
            return "🟡 MARKT GESCHLOSSEN (Pre/After)", "Vorsicht bei Spreads"
        else:
            return "🟢 MARKT AKTIV (LIVE)", "Volle Liquidität"

    def get_gmsi_data(self):
        # Holt Hintergrund-Daten (GMSI, VIX, DXY) via Yahoo (schont API Limits)
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

# --- MAIN LOGIC ---
state = load_state()
engine = TradingEngine()
tz_ch = pytz.timezone('Europe/Zurich')

if "last_run" not in st.session_state:
    st.session_state.last_run = datetime.now()

def perform_scalping_check():
    # 1. Daten holen
    gmsi_df = engine.get_gmsi_data()
    m_status, m_info = engine.get_market_status_info()
    
    # Status anzeigen
    status_cls = "status-online" if "AKTIV" in m_status else "status-offline"
    st.markdown(f'<div class="live-status {status_cls}">{m_status}<br><small>{m_info}</small></div>', unsafe_allow_html=True)

    for name in engine.td_map.keys():
        # Twelve Data Kerzen (Schnell)
        candles = engine.get_td_candles(name)
        if candles is None or len(candles) < 15: continue
        
        current_price = candles.iloc[-1]
        rsi = engine.calculate_rsi(candles).iloc[-1]
        
        # GMSI & VIX Daten (Yahoo)
        g_now, g_prev, dxy_now, vix = engine.calculate_gmsi(gmsi_df, name)
        
        decision = "ABWARTEN"
        conf = 0
        pattern = ""
        
        # A. VIX Check (Original Logik)
        if vix > 18: conf += 30
        
        # B. RSI Scalping Zonen (Angepasst auf 5min)
        if 25 <= rsi <= 35: conf += 30
        if 65 <= rsi <= 75: conf += 30
        
        # C. GMSI Muster (Original Logik angepasst auf Scalping)
        if g_now < g_prev: # Markt sinkt
            if rsi < 35: # Aber Asset ist überverkauft -> Krisen-Muster/Rebound
                decision = "KAUFEN"
                pattern = "Krisen-Muster / Rebound"
                conf += 30
        elif g_now > g_prev: # Markt steigt
            if rsi > 65: # Asset zu teuer -> Korrektur
                decision = "SHORTEN"
                pattern = "Überhitzung"
                conf += 30

        # D. Signal Logik
        if decision != "ABWARTEN" and conf >= 50:
            last_sig = state['last_notified'].get(name, "")
            # Melden wenn neu oder wenn 24h vergangen
            if last_sig != decision:
                # Scalping Ziele (enger als Swing)
                tp_dist = 0.006  # 0.6% Ziel
                sl_dist = 0.004  # 0.4% Stop
                
                tp = current_price * (1 + tp_dist) if decision == "KAUFEN" else current_price * (1 - tp_dist)
                sl = current_price * (1 - sl_dist) if decision == "KAUFEN" else current_price * (1 + sl_dist)
                
                msg = f"⚡ <b>SCALP-SIGNAL: {name}</b>\nAktion: {decision}\nMuster: {pattern}\nRSI: {rsi:.1f} | VIX: {vix:.1f}\nPreis: {current_price:.2f}\nTP: {tp:.2f}\nSL: {sl:.2f}"
                send_telegram_msg(msg)
                state['last_notified'][name] = decision
                save_state(state)
        
        # Pause für API Limit
        time.sleep(1.2)

# --- UI AUFBAU ---
st.title("⚡ Master Terminal Scalper (Lvl 5.2)")

if st.button("🔴 SCAN STARTEN (1x Loop)"):
    with st.spinner("Analysiere 5-Min Charts & GMSI..."):
        perform_scalping_check()
    st.success("Scan beendet.")

col_main, col_acc = st.columns([2, 1])

with col_acc:
    st.header("Portfolio")
    st.metric("Balance", f"{state['balance']:.2f} CHF")
    st.metric("Profit Realisiert", f"{state['total_profit']:.2f} CHF")
    
    if state['active_trades']:
        st.subheader("Offene Scalps")
        trades_to_close = []
        
        for asset, data in state['active_trades'].items():
            curr_p = engine.get_realtime_price(asset)
            if not curr_p: curr_p = data['entry']
            
            entry = data['entry']
            direction = data['dir']
            
            # PnL Berechnung
            if direction == "KAUFEN":
                pnl_pct = (curr_p - entry) / entry
            else:
                pnl_pct = (entry - curr_p) / entry
            
            pnl_chf = state['balance'] * 20 * pnl_pct # 20er Hebel simuliert
            
            # --- AUTO BREAK EVEN LOGIK ---
            be_triggered = False
            if pnl_pct > 0.004 and not data.get('be_active'): # Bei 0.4% Profit
                data['be_active'] = True
                data['sl_price'] = entry # SL auf 0 ziehen
                save_state(state)
                send_telegram_msg(f"🛡️ <b>BREAK-EVEN: {asset}</b>\nStop-Loss auf Einstieg gezogen!")
                be_triggered = True
            
            # --- STOP LOSS CHECK ---
            sl_hit = False
            if 'sl_price' in data:
                if direction == "KAUFEN" and curr_p < data['sl_price']: sl_hit = True
                if direction == "SHORTEN" and curr_p > data['sl_price']: sl_hit = True
            
            # Anzeige
            status_color = "#16a34a" if pnl_chf > 0 else "#dc2626"
            be_icon = "🛡️" if data.get('be_active') else ""
            
            st.markdown(f"""
            <div class="active-trade-box">
                <b>{asset} {be_icon}</b><br>
                {direction} @ {entry:.2f}<br>
                Aktuell: {curr_p:.2f}<br>
                PnL: <span style="color:{status_color};font-weight:bold;">{pnl_chf:.2f} CHF</span>
            </div>
            """, unsafe_allow_html=True)
            
            if sl_hit:
                st.error(f"{asset}: SL/BE hit!")
                if st.button(f"Close {asset}", key=f"sl_{asset}"):
                    trades_to_close.append((asset, pnl_chf))

            if st.button(f"Manuell Close {asset}", key=f"man_{asset}"):
                trades_to_close.append((asset, pnl_chf))
        
        # Trades schließen
        for asset, pnl in trades_to_close:
            state['balance'] += pnl 
            state['total_profit'] += pnl
            del state['active_trades'][asset]
            save_state(state)
            st.rerun()

with col_main:
    st.info("System läuft auf 5-Minuten Basis (High Speed). Marktstatus wird geprüft.")
    
    if st.button("Manuelles Trade-Panel öffnen"):
        with st.expander("Scalp eröffnen", expanded=True):
            s_asset = st.selectbox("Asset", list(engine.td_map.keys()))
            s_dir = st.selectbox("Richtung", ["KAUFEN", "SHORTEN"])
            s_price = st.number_input("Einstiegspreis", value=0.0)
            
            if st.button("Trade eintragen"):
                state['active_trades'][s_asset] = {
                    "entry": s_price,
                    "dir": s_dir,
                    "t212_val": state['balance'] * 20, 
                    "be_active": False,
                    "sl_price": s_price * 0.996 if s_dir == "KAUFEN" else s_price * 1.004
                }
                save_state(state)
                st.success(f"{s_asset} Scalp gestartet!")
                st.rerun()
