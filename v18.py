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

st.set_page_config(page_title="Master Terminal Lvl 9.0 - Precision Matrix", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #ffffff; color: #1e293b; }
    .stMetric { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; }
    .instruction-card { background-color: #ffffff; border: 1px solid #e2e8f0; border-left: 6px solid #2563eb; padding: 25px; border-radius: 8px; margin-bottom: 25px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
    .t212-value { color: #2563eb; font-size: 2.8rem; font-weight: 900; display: block; margin: 10px 0; }
    .stButton>button { background-color: #2563eb !important; color: white !important; font-weight: bold; width: 100%; height: 55px; border-radius: 12px; border: none; font-size: 1.1rem; }
    .glasklar { font-size: 2.5rem; font-weight: 900; text-transform: uppercase; color: #1e293b; border-bottom: 4px solid #2563eb; display: inline-block; margin-bottom: 15px; }
    .time-box { background-color: #e0f2fe; border: 1px solid #0ea5e9; color: #0369a1; padding: 10px; border-radius: 8px; text-align: center; margin-top: 10px; font-weight: bold; }
    .active-trade-box { background-color: #f0fdf4; border: 1px solid #16a34a; border-radius: 10px; padding: 15px; margin-bottom: 15px; }
    .live-status { padding: 15px; border-radius: 10px; font-weight: bold; text-align: center; margin-bottom: 20px; border: 1px solid #e2e8f0; }
    .status-online { background-color: #dcfce7; color: #166534; border-color: #16a34a; }
    .status-warn { background-color: #fef9c3; color: #854d0e; border-color: #eab308; }
    .status-offline { background-color: #fee2e2; color: #991b1b; border-color: #ef4444; }
    .tp-box { background-color: #f0fdf4; padding: 10px; border-radius: 8px; border: 1px solid #16a34a; flex: 1; text-align: center; }
    .sl-box { background-color: #fff1f2; padding: 10px; border-radius: 8px; border: 1px solid #be123c; flex: 1; text-align: center; }
    </style>
""", unsafe_allow_html=True)

TELEGRAM_TOKEN = "8500617608:AAHpWCJa24KU_GGq70ewQvb4s2sKj-DfDkI"
TELEGRAM_CHAT_ID = "8098807031"

def send_telegram_msg(message):
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

state = load_state()

class TradingEngine:
    def __init__(self):
        self.asset_config = {
            'GOLD': ['GC=F', 'XAUUSD=X'],
            'SILBER': ['SI=F', 'XAGUSD=X'],
            'PLATIN': ['PL=F', 'XPTUSD=X'],
            'WTI_ÖL': ['CL=F', 'CL=F'],    
            'KUPFER': ['HG=F', 'HG=F']     
        }
        self.gmsi_tickers = {'USA': 'SPY', 'EU': '^GDAXI', 'CHINA': '000001.SS', 'JAPAN': '^N225'}
        self.drivers = {'VIX': '^VIX', 'TREASURY_10Y': '^TNX', 'USD_INDEX': 'DX-Y.NYB', 'MINERS': 'GDX', 'BTC': 'BTC-USD'}
        self.active_tickers = {} 

    def fetch_data(self):
        all_symbols = set()
        for variants in self.asset_config.values():
            all_symbols.update(variants)
        all_symbols.update(self.gmsi_tickers.values())
        all_symbols.update(self.drivers.values())
        try:
            data_1h = yf.download(list(all_symbols), period="5d", interval="1h", progress=False)['Close'].ffill()
            data_1d = yf.download(list(all_symbols), period="100d", interval="1d", progress=False)['Close'].ffill()
            if data_1h.empty or data_1d.empty: return None, None
            return data_1h, data_1d
        except: return None, None

    def get_best_price_series(self, df, asset_name):
        variants = self.asset_config[asset_name]
        for ticker in variants:
            if ticker in df.columns:
                series = df[ticker].dropna()
                if not series.empty:
                    self.active_tickers[asset_name] = ticker
                    return series, ticker
        return None, None

    def calculate_gmsi(self, df_h, asset_name):
        t = self.gmsi_tickers
        if not all(t[k] in df_h.columns for k in t): return None
        usa, eu, china, japan = df_h[t['USA']], df_h[t['EU']], df_h[t['CHINA']], df_h[t['JAPAN']]
        w_china = 0.30 if asset_name in ['KUPFER', 'WTI_ÖL'] else 0.15
        w_japan = 1.0 - 0.50 - 0.20 - w_china
        return (usa * 0.50) + (eu * 0.20) + (china * w_china) + (japan * w_japan)

    def calculate_atr(self, series, period=14):
        return (series.rolling(2).max() - series.rolling(2).min()).rolling(period).mean().iloc[-1]

    def perform_analysis(self):
        df_h, df_d = self.fetch_data()
        if df_h is None or df_d is None: return None, []
        
        vix = df_h[self.drivers['VIX']].iloc[-1] if self.drivers['VIX'] in df_h.columns else 20
        dxy_ch = df_h[self.drivers['USD_INDEX']].pct_change(fill_method=None).rolling(5).sum().iloc[-1] if self.drivers['USD_INDEX'] in df_h.columns else 0
        
        analysis_results = []
        current_hour = datetime.now().hour
        market_open = current_hour >= 8

        for name in self.asset_config.keys():
            p_h, ticker_used = self.get_best_price_series(df_h, name)
            p_d, _ = self.get_best_price_series(df_d, name)
            if p_h is None or p_d is None: continue
            
            p_now = p_h.iloc[-1]
            
            d_t = "UP" if p_d.iloc[-1] > p_d.iloc[-5] else "DOWN"
            h1_t = "UP" if p_h.iloc[-1] > p_h.iloc[-10] else "DOWN"
            
            gmsi_s = self.calculate_gmsi(df_h, name)
            if gmsi_s is None: continue
            
            ratio_s = p_h / gmsi_s
            ratio_now = ratio_s.iloc[-1]
            ratio_sma = ratio_s.rolling(50).mean().iloc[-1]
            
            conf = 0.0
            
            if d_t == h1_t: conf += 40.0
            
            dist = (ratio_now - ratio_sma) / ratio_sma
            if (dist > 0 and d_t == "UP"): conf += 20.0
            elif (dist < 0 and d_t == "DOWN"): conf += 20.0
            
            if name in ['GOLD', 'SILBER']:
                if dxy_ch < 0: conf += 10.0
                if vix > 20: conf += 10.0
            
            g_ch = gmsi_s.pct_change(fill_method=None).rolling(5).sum().iloc[-1]
            p_ch = p_h.pct_change(fill_method=None).rolling(5).sum().iloc[-1]
            if name == 'GOLD':
                if g_ch < -0.002 and p_ch > -0.001: conf += 20.0
                elif g_ch > 0.002 and p_ch > 0.002: conf += 20.0
            else:
                 if (g_ch > 0 and d_t == "UP") or (g_ch < 0 and d_t == "DOWN"): conf += 20.0

            if d_t != h1_t:
                conf = min(conf, 49.0)

            conf = min(max(conf, 0), 100)

            hourly_atr = self.calculate_atr(p_h)
            vola_pct = (hourly_atr / p_now) * 100
            
            if vola_pct > 0:
                base_lev = 4.0 / vola_pct 
            else: 
                base_lev = 1
                
            base_lev = min(max(base_lev, 1), 20)
            
            conf_factor = conf / 100.0
            final_lev = int(base_lev * (conf_factor * conf_factor))
            final_lev = max(1, final_lev)
            
            decision = "ABWARTEN"
            if market_open:
                if conf >= 70 and d_t == "UP": decision = "KAUFEN"
                elif conf >= 70 and d_t == "DOWN": decision = "SHORTEN"
            
            estimated_duration = 0
            sl_dist_abs = 0
            if hourly_atr > 0:
                sl_dist_abs = hourly_atr * 2.0
                tp_dist = hourly_atr * 3.0
                estimated_duration = min(max(tp_dist / hourly_atr, 2), 10)

            is_spot = "USD=X" in ticker_used
            ticker_label = f"{ticker_used} ({'SPOT' if is_spot else 'FUT'})"

            res = {
                'name': name, 'ticker': ticker_label, 'raw_ticker': ticker_used,
                'p': p_now, 'conf': round(conf, 1), 'h': final_lev, 
                'dir': decision, 'vola': vola_pct, 'aligned': (d_t == h1_t),
                'est_hours': estimated_duration, 'hourly_atr': hourly_atr,
                'sl_dist_abs': sl_dist_abs
            }
            analysis_results.append(res)
            
        return df_h, analysis_results




def check_data_integrity(df_h):
    if df_h is None or df_h.empty: return False, "OFFLINE: KEINE DATEN"
    now_utc = datetime.now(pytz.utc)
    last_ts = df_h.index[-1]
    if last_ts.tzinfo is None: last_ts = pytz.utc.localize(last_ts)
    diff_minutes = (now_utc - last_ts).total_seconds() / 60
    
    if diff_minutes < 15: return True, "🟢 DATEN AKTUELL (OK für Daytrading)"
    elif diff_minutes < 60: return True, f"⚠️ VERZÖGERT ({int(diff_minutes)} min) - OK für Trend"
    else: return True, f"🔴 VERALTET ({int(diff_minutes)} min)"

def display_live_status(status_msg):
    if "AKTUELL" in status_msg: style = "status-online"
    elif "VERZÖGERT" in status_msg: style = "status-warn"
    else: style = "status-offline"
    st.markdown(f'<div class="live-status {style}">{status_msg} | {datetime.now().strftime("%H:%M:%S")}</div>', unsafe_allow_html=True)

engine = TradingEngine()
st.title("🛡️ Master Terminal Lvl 9.0 - Precision Matrix")
col_main, col_acc = st.columns([2, 1])

with st.spinner("🔄 Multi-Faktor Analyse & Hebel-Berechnung..."):
    df_live, results = engine.perform_analysis()
    res_map = {r['name']: r for r in results}

with col_acc:
    st.header("🏦 Depot")
    bal = st.number_input("Kapital (CHF)", value=float(state['balance']))
    if bal != state['balance']:
        state['balance'] = bal
        save_state(state)
    st.metric("Gesamtprofit", f"{state['total_profit']:.2f} CHF")
    
    if st.button("🔔 TEST-NACHRICHT SENDEN"):
        send_telegram_msg("🤖 <b>SYSTEM-CHECK ERFOLGREICH!</b>\nDer Bot ist verbunden und bereit für Signale.")
        st.success("Test gesendet! Prüfe dein Telegram.")

    if st.button("📤 SIGNALE MANUELL PUSHEN"):
        sent_count = 0
        for r in results:
            if r['dir'] != "ABWARTEN":
                sl_p = r['p'] - r['sl_dist_abs'] if r['dir'] == "KAUFEN" else r['p'] + r['sl_dist_abs']
                tp_dist = r['sl_dist_abs'] * 1.5 
                tp_p = r['p'] + tp_dist if r['dir'] == "KAUFEN" else r['p'] - tp_dist
                t212_val = (state['balance']) * r['h'] * 0.5 
                exit_time_calc = datetime.now() + timedelta(hours=r['est_hours'])
                exit_str = exit_time_calc.strftime("%H:%M")
                
                msg = f"🔄 <b>MANUELLER PUSH: {r['name']}</b>\nTrend: {r['dir']}\n\n💰 <b>T212 EINSATZ: {t212_val:.0f}</b> (Hebel {r['h']}x)\n\nEntry: {r['p']:.4f}\n🎯 TP: {tp_p:.4f}\n🛑 SL: {sl_p:.4f}\n\n⏰ <b>Plan-Exit: {exit_str} Uhr</b>"
                send_telegram_msg(msg)
                sent_count += 1
        if sent_count > 0: st.success(f"{sent_count} Signale gesendet!")
        else: st.warning("Keine Signale verfügbar.")
    
    if state['active_trades']:
        st.subheader("🟢 Offene Trades")
        for asset, data in list(state['active_trades'].items()):
            used_ticker = engine.active_tickers.get(asset)
            if used_ticker and used_ticker in df_live.columns:
                current_p = df_live[used_ticker].iloc[-1]
            else: current_p = data['entry'] 
            
            dir_mult = 1 if data['dir'] == "KAUFEN" else -1
            spread_cost = 0.05
            pnl_pct = (((current_p - data['entry']) / data['entry']) * 100 * dir_mult) - spread_cost
            pnl_chf = (data['t212_val'] * pnl_pct) / 100
            
            if 'exit_ts' in data:
                try:
                    exit_dt = datetime.fromisoformat(data['exit_ts'])
                    now = datetime.now()
                    time_left = (exit_dt - now).total_seconds() / 60
                    if 0 < time_left <= 5 and not data.get('exit_warning_sent'):
                        warn_msg = f"⏰ <b>5-MINUTEN WARNUNG: {asset}</b>\n\nGeplanter Exit erreicht!\nBitte Position prüfen und ggf. schließen."
                        send_telegram_msg(warn_msg)
                        state['active_trades'][asset]['exit_warning_sent'] = True
                        save_state(state)
                    time_display = f"⏰ Exit: {exit_dt.strftime('%H:%M')} ({int(time_left)} min)"
                except: time_display = "⏰ Exit: Unbekannt"
            else: time_display = ""
            
            analysis = res_map.get(asset)
            current_vola = analysis['vola'] if analysis else 0.5
            dynamic_be_threshold = max(0.005, current_vola / 100 * 1.0) 
            be_active = pnl_pct >= (dynamic_be_threshold * 100)

            if be_active and not state.get('be_notified', {}).get(asset):
                msg = f"🛡️ <b>BREAK-EVEN: {asset}</b>\nProfit: {pnl_pct:.2f}%\nStopp auf Einstieg nachziehen!"
                send_telegram_msg(msg)
                if 'be_notified' not in state: state['be_notified'] = {}
                state['be_notified'][asset] = True
                save_state(state)

            color = "#16a34a" if pnl_chf > 0 else "#dc2626"
            st.markdown(f"""
                <div class="active-trade-box">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <b>{asset} ({data['dir']})</b>
                        <b style="color:{color}; font-size:1.2rem;">{pnl_pct:.2f}%</b>
                    </div>
                    <div style="font-size:0.8rem; color:#64748b; margin-top:5px;">
                        Einstieg: {data['entry']:.4f} | P&L: {pnl_chf:.2f} CHF<br>
                        <span style="color:#ef4444; font-size:0.7rem;">(inkl. Spread-Sim ~0.05%)</span><br>
                        <b>{time_display}</b>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            exit_key = f"exp_{asset}"
            if st.button(f"🏁 Abrechnung: {asset}", key=f"btn_{asset}"):
                st.session_state[exit_key] = not st.session_state.get(exit_key, False)

            if st.session_state.get(exit_key, False):
                with st.container(border=True):
                    final_pnl = st.number_input("Finaler P&L (CHF)", value=float(round(pnl_chf, 2)), key=f"pnl_in_{asset}")
                    if st.button("✅ BESTÄTIGEN", key=f"conf_{asset}"):
                        state['total_profit'] += final_pnl
                        state['last_notified'][asset] = "RESET"
                        if asset in state.get('be_notified', {}): del state['be_notified'][asset]
                        del state['active_trades'][asset]
                        st.session_state[exit_key] = False
                        save_state(state)
                        st.rerun()




with col_main:
    if df_live is not None:
        gold_ticker = engine.active_tickers.get('GOLD', 'GC=F')
        if gold_ticker in df_live.columns:
            ref_series = df_live[[gold_ticker]]
            _, status_msg = check_data_integrity(ref_series)
            display_live_status(status_msg)
    
    for r in results:
        trend_icon = "🟢 ↗️" if r['dir'] == "KAUFEN" else "🔴 ↘️" if r['dir'] == "SHORTEN" else "⚪ ➡️"
        exp_label = f"{trend_icon} {r['name']} | Preis: {r['p']:.2f} | Conf: {r['conf']}% | Hebel: {r['h']}x"
        
        with st.expander(exp_label, expanded=(r['dir'] != "ABWARTEN")):
            if r['name'] == 'GOLD':
                 gmsi_series = engine.calculate_gmsi(df_live, 'GOLD')
                 if gmsi_series is not None:
                    chart_data = pd.DataFrame({
                        "GOLD": (df_live[r['raw_ticker']].tail(50) / df_live[r['raw_ticker']].tail(50).iloc[0] - 1)*100,
                        "GMSI": (gmsi_series.tail(50) / gmsi_series.tail(50).iloc[0] - 1)*100
                    })
                    st.line_chart(chart_data, color=["#FFD700", "#1E293B"])

            if r['dir'] != "ABWARTEN":
                sl_p = r['p'] - r['sl_dist_abs'] if r['dir'] == "KAUFEN" else r['p'] + r['sl_dist_abs']
                tp_dist = r['sl_dist_abs'] * 1.5 
                tp_p = r['p'] + tp_dist if r['dir'] == "KAUFEN" else r['p'] - tp_dist
                t212_val = (state['balance']) * r['h'] * 0.5 
                
                exit_time = datetime.now() + timedelta(hours=r['est_hours'])
                exit_time_str = exit_time.strftime("%H:%M")
                exit_ts_iso = exit_time.isoformat()
                
                if state['last_notified'].get(r['name']) != r['dir']:
                    msg = f"🌅 <b>SIGNAL: {r['name']}</b>\nTrend: {r['dir']}\n\n💰 <b>T212 EINSATZ: {t212_val:.0f}</b> (Hebel {r['h']}x)\n\nEntry: {r['p']:.4f}\n🎯 TP: {tp_p:.4f}\n🛑 SL: {sl_p:.4f}\n\n⏰ <b>Plan-Exit: {exit_time_str} Uhr</b>"
                    send_telegram_msg(msg)
                    state['last_notified'][r['name']] = r['dir']
                    save_state(state)
                
                st.markdown(f"### <span class='glasklar'>{r['dir']}</span>", unsafe_allow_html=True)
                st.info(f"📊 Matrix-Hebel: {r['h']}x (Volatilität: {r['vola']:.2f}% | Sicherheit: {r['conf']}%)")
                
                st.markdown(f"""
                    <div style="background-color:#f8fafc; padding:15px; border-radius:10px; border:1px solid #e2e8f0; margin:10px 0;">
                        <span style="color:#64748b; font-size:0.9rem;">EMPFOHLENER EINSATZ ({r['h']}x):</span><br>
                        <span class='t212-value'>{t212_val:.0f} CHF</span>
                    </div>
                    
                    <div style="display:flex; gap:10px; margin-bottom:10px;">
                        <div class="tp-box">
                            <span style="color:#166534; font-size:0.8rem;">TAKE PROFIT (Ziel)</span><br>
                            <b style="font-size:1.2rem;">{tp_p:.4f}</b>
                        </div>
                        <div class="sl-box">
                            <span style="color:#991b1b; font-size:0.8rem;">STOP LOSS (Schutz)</span><br>
                            <b style="font-size:1.2rem;">{sl_p:.4f}</b>
                        </div>
                    </div>
                    
                    <div class="time-box">
                        ⏳ Geschätzte Dauer: {int(r['est_hours'])} Stunden<br>
                        ⏰ Planmäßiger Exit: ca. {exit_time_str} Uhr<br>
                    </div>
                """, unsafe_allow_html=True)
                
                entry_in = st.number_input(f"Einstieg {r['name']}", value=float(r['p']), format="%.4f", key=f"in_{r['name']}")
                
                if st.button(f"Trade {r['name']} starten", key=f"start_{r['name']}"):
                    state['active_trades'][r['name']] = {
                        "entry": entry_in, 
                        "dir": r['dir'], 
                        "t212_val": t212_val, 
                        "h": r['h'],
                        "exit_ts": exit_ts_iso,
                        "exit_warning_sent": False
                    }
                    save_state(state)
                    st.rerun()
            else:
                st.info(f"Kein klares Signal. Trends (D1/H1) widersprüchlich oder GMSI neutral.")

time.sleep(60) 
st.rerun()
