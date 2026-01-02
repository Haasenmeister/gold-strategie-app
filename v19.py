import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from datetime import datetime
import pytz

# --- KONFIGURATION ---
st.set_page_config(page_title="SNIPER V17 - FINAL", layout="wide")

# --- CSS STYLING (Hell & Sauber) ---
st.markdown("""
    <style>
    /* Grundgerüst */
    .stApp { background-color: #f8fafc; color: #0f172a; }
    
    /* Boxen Designs */
    .success-box {
        background-color: #ffffff;
        border: 2px solid #22c55e;
        border-radius: 15px;
        padding: 25px;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    
    .fail-box {
        background-color: #ffffff;
        border: 2px solid #ef4444;
        border-radius: 15px;
        padding: 20px;
        text-align: center;
        color: #64748b;
        opacity: 0.9;
    }
    
    /* Geld Anzeige */
    .money-display {
        background-color: #dcfce7;
        border: 2px solid #86efac;
        color: #14532d;
        padding: 20px;
        border-radius: 10px;
        margin: 20px 0;
    }
    
    /* Checklisten Styles */
    .check-container {
        text-align: left;
        background-color: #f1f5f9;
        padding: 15px;
        border-radius: 10px;
        margin-top: 15px;
        font-size: 0.95rem;
        line-height: 1.6;
    }
    
    .status-ok { color: #166534; font-weight: bold; }
    .status-fail { color: #dc2626; font-weight: bold; }
    
    /* Text Styles */
    .asset-title { font-size: 3rem; font-weight: 900; color: #0f172a; margin: 0; }
    .direction-long { color: #16a34a; font-size: 1.5rem; font-weight: bold; }
    .direction-short { color: #dc2626; font-size: 1.5rem; font-weight: bold; }
    .big-money { font-size: 2.5rem; font-weight: 900; }
    
    </style>
""", unsafe_allow_html=True)

# --- TELEGRAM CONFIG ---
TELEGRAM_TOKEN = "8500617608:AAHpWCJa24KU_GGq70ewQvb4s2sKj-DfDkI"
TELEGRAM_CHAT_ID = "8098807031"

def send_telegram(msg):
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=3)
    except: pass

# --- ANALYSE ENGINE ---
class SniperEngine:
    def __init__(self):
        self.targets = {
            'GOLD': 'GC=F', 'SILBER': 'SI=F', 'WTI_ÖL': 'CL=F', 
            'DAX': '^GDAXI', 'NASDAQ': 'NQ=F'
        }
        self.macro = {'DXY': 'DX-Y.NYB'}

    def get_data(self):
        tickers = list(self.targets.values()) + list(self.macro.values())
        try:
            data_h = yf.download(tickers, period="5d", interval="1h", progress=False)['Close'].ffill()
            data_d = yf.download(tickers, period="50d", interval="1d", progress=False)['Close'].ffill()
            return data_h, data_d
        except: return None, None

    def rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def analyze(self):
        df_h, df_d = self.get_data()
        if df_h is None or df_d is None: return None, 0, "No Data"
        
        last_ts = df_h.index[-1]
        if last_ts.tzinfo is None: last_ts = pytz.utc.localize(last_ts)
        now_utc = datetime.now(pytz.utc)
        delay_minutes = int((now_utc - last_ts).total_seconds() / 60)
        data_time_str = last_ts.astimezone(pytz.timezone('Europe/Zurich')).strftime('%H:%M')
        
        candidates = []
        dxy_trend = "NEUTRAL"
        if self.macro['DXY'] in df_h.columns:
            dxy = df_h[self.macro['DXY']].dropna()
            if not dxy.empty: dxy_trend = "UP" if dxy.iloc[-1] > dxy.iloc[-10] else "DOWN"
        
        for name, ticker in self.targets.items():
            if ticker not in df_h.columns or ticker not in df_d.columns: continue
            
            p_h = df_h[ticker].dropna() 
            p_d = df_d[ticker].dropna() 
            if p_h.empty or p_d.empty: continue
            
            curr_p = p_h.iloc[-1]
            
            # Indikatoren
            sma50_d = p_d.rolling(50).mean().iloc[-1]
            daily_trend = "UP" if p_d.iloc[-1] > sma50_d else "DOWN"
            
            sma50_h = p_h.rolling(50).mean().iloc[-1]
            sma20_h = p_h.rolling(20).mean().iloc[-1]
            hourly_trend = "NEUTRAL"
            if curr_p > sma50_h and sma20_h > sma50_h: hourly_trend = "UP"
            elif curr_p < sma50_h and sma20_h < sma50_h: hourly_trend = "DOWN"
            
            rsi_val = self.rsi(p_h).iloc[-1]
            
            score = 0
            checks = []
            direction = "NEUTRAL"
            
            # 1. TREND CHECK
            if daily_trend == hourly_trend and hourly_trend != "NEUTRAL":
                score += 50
                direction = "LONG" if daily_trend == "UP" else "SHORT"
                checks.append(f"✅ Trend Konvergenz: D1 {daily_trend} + H1 {hourly_trend}")
            else:
                score -= 100
                checks.append(f"❌ Trend Konflikt: D1 {daily_trend} vs H1 {hourly_trend}")
                direction = "NEUTRAL"

            # 2. RSI CHECK
            if direction == "LONG":
                if 45 <= rsi_val <= 68: 
                    score += 20
                    checks.append(f"✅ RSI Gesund ({rsi_val:.0f})")
                elif rsi_val > 70: 
                    score -= 50
                    checks.append(f"❌ RSI Überkauft ({rsi_val:.0f})")
            elif direction == "SHORT":
                if 32 <= rsi_val <= 55: 
                    score += 20
                    checks.append(f"✅ RSI Gesund ({rsi_val:.0f})")
                elif rsi_val < 30: 
                    score -= 50
                    checks.append(f"❌ RSI Überverkauft ({rsi_val:.0f})")

            # 3. VOLATILITÄT
            try:
                avg_move_5 = p_h.diff().abs().rolling(5).mean().iloc[-1]
                curr_move = abs(p_h.iloc[-1] - p_h.iloc[-2])
                if pd.isna(avg_move_5) or avg_move_5 == 0:
                    checks.append("⚠️ Vola-Daten unklar")
                elif curr_move < (avg_move_5 * 0.2):
                    score -= 30
                    checks.append("❌ Markt schläft (Vola zu tief)")
                else:
                    score += 10
                    checks.append("✅ Volatilität aktiv")
            except: pass

            # 4. MACRO
            if name in ['GOLD', 'SILBER', 'WTI_ÖL']:
                if direction == "LONG" and dxy_trend == "DOWN": 
                    score += 20
                    checks.append("✅ Dollar schwach (Gut)")
                elif direction == "SHORT" and dxy_trend == "UP": 
                    score += 20
                    checks.append("✅ Dollar stark (Gut)")
                elif direction != "NEUTRAL": 
                    score -= 20
                    checks.append(f"❌ Dollar Gegenwind ({dxy_trend})")
            
            candidates.append({
                'name': name,
                'dir': direction,
                'price': curr_p,
                'score': max(0, score),
                'rsi': rsi_val,
                'checks': checks,
                'stop_loss': curr_p * 0.99 if direction == "LONG" else curr_p * 1.01
            })

        best = sorted(candidates, key=lambda x: x['score'], reverse=True)[0] if candidates else None
        return best, delay_minutes, data_time_str

# --- STATE MANAGEMENT ---
if 'last_scan' not in st.session_state:
    st.session_state['last_scan'] = None
if 'exposure_val' not in st.session_state:
    st.session_state['exposure_val'] = 0.0

# --- SIDEBAR EINGABEN ---
with st.sidebar:
    st.title("🛡️ SNIPER V17")
    st.markdown("### ⚙️ Kapital-Setup")
    
    # User gibt sein Kapital ein (z.B. 5000)
    user_balance = st.number_input("Dein Kontostand (CHF)", value=5000.0, step=100.0)
    
    # RECHNUNG: Voller Einsatz * 5
    # Das ist der Wert, den der Bot senden soll
    total_exposure = user_balance * 5.0
    
    # Speichern im State für später
    st.session_state['exposure_val'] = total_exposure
    
    st.success(f"""
    **Berechnung für Bot:**
    Kontostand: {user_balance:,.0f} CHF
    Hebel: 5x
    
    👉 **Sende-Wert: {total_exposure:,.0f} CHF**
    """)
    
    st.markdown("---")
    st.info("⏰ **Zeiten:**\n08:15-08:45 (London)\n14:45-15:15 (US)")

# --- HAUPTSEITE ---
engine = SniperEngine()
st.subheader("Markt-Scanner (Final Edition)")

col1, col2 = st.columns([3, 1])

with col1:
    # 1. SCAN BUTTON
    if st.button("🔎 JETZT SCANNEN", type="primary", use_container_width=True):
        with st.spinner("Prüfe Märkte & Trends..."):
            target, delay, data_time = engine.analyze()
            st.session_state['last_scan'] = target
            st.session_state['scan_delay'] = delay

    # 2. ERGEBNIS ANZEIGE
    if st.session_state['last_scan']:
        target = st.session_state['last_scan']
        
        # HTML STRING BAUEN (Hier war der Fehler früher - jetzt vereinfacht)
        checks_html = ""
        for c in target['checks']:
            css_class = "status-ok" if "✅" in c else "status-fail" if "❌" in c else ""
            checks_html += f"<div class='{css_class}'>{c}</div>"

        # FALL A: TREFFER
        if target['score'] >= 80:
            color = "#22c55e" # Grün
            dir_cls = "direction-long" if target['dir'] == "LONG" else "direction-short"
            arrow = "📈" if target['dir'] == "LONG" else "📉"
            
            # Robuste HTML Anzeige
            st.markdown(f"""
            <div class="success-box">
                <h3 style="color:#64748b; margin:0;">ZIEL ERFASST</h3>
                <div class="asset-title">{target['name']}</div>
                <div class="{dir_cls}">{arrow} {target['dir']}</div>
                
                <div class="money-display">
                    <div>EINGABE-WERT (INKL. 5x HEBEL):</div>
                    <div class="big-money">{st.session_state['exposure_val']:,.2f} CHF</div>
                    <div>Stop Loss: <b>{target['stop_loss']:.4f}</b></div>
                </div>
                
                <div class="check-container">
                    <b>📋 Analyse-Details:</b><br>
                    {checks_html}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # BOT BUTTON
            if st.button(f"🚀 AN BOT SENDEN: {target['name']}", type="secondary", use_container_width=True):
                # Hier senden wir den berechneten 5x Wert!
                msg = (f"🎯 <b>SNIPER ORDER</b>\n\n"
                       f"Asset: <b>{target['name']}</b>\n"
                       f"Richtung: <b>{target['dir']}</b>\n"
                       f"Score: {target['score']}%\n\n"
                       f"💵 <b>EINGABE WERT (5x): {st.session_state['exposure_val']:,.2f} CHF</b>\n"
                       f"🛑 SL: {target['stop_loss']:.4f}\n"
                       f"✅ Checks: OK")
                send_telegram(msg)
                st.success("✅ Befehl gesendet!")
        
        # FALL B: KEIN TREFFER
        else:
            st.markdown(f"""
            <div class="fail-box">
                <h3>⛔ BLOCKIERT: {target['name']}</h3>
                <p>Score: {target['score']}/80 - Zu riskant.</p>
                <div class="check-container">
                    {checks_html}
                </div>
            </div>
            """, unsafe_allow_html=True)
            st.info("Disziplin bewahren. Warten.")

with col2:
    st.write("")
    st.markdown("### Status")
    tz = pytz.timezone('Europe/Zurich')
    now = datetime.now(tz)
    
    if (now.hour == 8 and 15 <= now.minute <= 45):
        st.success("🟢 LONDON OPEN")
    elif (now.hour == 14 and 45 <= now.minute <= 59) or (now.hour == 15 and now.minute <= 15):
        st.success("🟠 US OPEN")
    elif now.hour >= 18:
        st.error("🌙 CLOSED")
    else:
        st.warning(f"⚪ STANDBY ({now.strftime('%H:%M')})")
