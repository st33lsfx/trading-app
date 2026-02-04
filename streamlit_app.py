import streamlit as st
import pandas as pd
import os
import time
from bot import TradingBot
from backtest import Backtester
from economic_data import get_economic_calendar, is_market_volatile_today

# Page Config
st.set_page_config(
    page_title="Trading Bot 3.0 | Neon",
    page_icon="🎮",
    layout="wide"
)

# ============================================
# HELPER: Get secrets (Streamlit Cloud + Local)
# ============================================
def get_secret(key, default=None):
    """
    Get secret from Streamlit Cloud secrets or fall back to environment variable.
    Works both on Streamlit Cloud and local development.
    """
    try:
        # Try Streamlit secrets first (for Streamlit Cloud)
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        # Fall back to environment variable (for local development)
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        return os.getenv(key, default)

# ============================================
# CUSTOM CSS THEME - "Neon Cyberpunk" Design v3.0
# ============================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

    /* === COLOR PALETTE === */
    :root {
        --bg-deep: #0a0f1c;
        --bg-card: rgba(16, 24, 40, 0.7);
        --bg-card-hover: rgba(25, 35, 55, 0.8);
        --neon-cyan: #00f5ff;
        --neon-pink: #ff00aa;
        --neon-green: #00ff88;
        --neon-red: #ff4444;
        --neon-yellow: #ffdd00;
        --text-primary: #ffffff;
        --text-secondary: #8892a6;
        --border-glow: rgba(0, 245, 255, 0.2);
        --grid-color: rgba(0, 245, 255, 0.03);
    }
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    code, .stCodeBlock, [class*="stDataFrame"] td, [class*="stDataFrame"] th {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* === MAIN BACKGROUND WITH GRID === */
    .stApp {
        background-color: var(--bg-deep);
        background-image: 
            linear-gradient(rgba(0, 245, 255, 0.02) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 245, 255, 0.02) 1px, transparent 1px),
            radial-gradient(ellipse at 20% 0%, rgba(0, 245, 255, 0.08) 0%, transparent 50%),
            radial-gradient(ellipse at 80% 100%, rgba(255, 0, 170, 0.06) 0%, transparent 50%);
        background-size: 50px 50px, 50px 50px, 100% 100%, 100% 100%;
    }

    /* === SIDEBAR - Cyberpunk Panel === */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(10, 15, 28, 0.95) 0%, rgba(16, 24, 40, 0.9) 100%) !important;
        border-right: 1px solid var(--border-glow);
        box-shadow: 4px 0 30px rgba(0, 245, 255, 0.05);
    }
    
    [data-testid="stSidebar"] .stButton button {
        background: linear-gradient(135deg, rgba(0, 245, 255, 0.1) 0%, rgba(255, 0, 170, 0.1) 100%);
        border: 1px solid var(--neon-cyan);
        color: var(--neon-cyan);
        text-shadow: 0 0 10px rgba(0, 245, 255, 0.5);
        transition: all 0.3s ease;
    }
    
    [data-testid="stSidebar"] .stButton button:hover {
        background: linear-gradient(135deg, rgba(0, 245, 255, 0.2) 0%, rgba(255, 0, 170, 0.2) 100%);
        box-shadow: 0 0 20px rgba(0, 245, 255, 0.3), inset 0 0 20px rgba(0, 245, 255, 0.1);
        transform: translateY(-2px);
    }
    
    /* === METRIC CARDS - Neon Glass === */
    [data-testid="stMetric"] {
        background: var(--bg-card);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid var(--border-glow);
        border-radius: 16px;
        padding: 24px;
        position: relative;
        overflow: hidden;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    [data-testid="stMetric"]::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, var(--neon-cyan), var(--neon-pink));
        opacity: 0;
        transition: opacity 0.3s;
    }
    
    [data-testid="stMetric"]:hover {
        border-color: var(--neon-cyan);
        transform: translateY(-6px);
        box-shadow: 
            0 20px 40px rgba(0, 0, 0, 0.3),
            0 0 30px rgba(0, 245, 255, 0.1),
            inset 0 0 30px rgba(0, 245, 255, 0.02);
    }
    
    [data-testid="stMetric"]:hover::before {
        opacity: 1;
    }
    
    [data-testid="stMetricLabel"] {
        color: var(--text-secondary) !important;
        font-size: 0.75rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 1.5px;
    }
    
    [data-testid="stMetricValue"] {
        color: var(--text-primary) !important;
        font-size: 2.2rem !important;
        font-weight: 700 !important;
        text-shadow: 0 0 20px rgba(255, 255, 255, 0.1);
    }
    
    /* === TABS - Neon Selector === */
    .stTabs [data-baseweb="tab-list"] {
        background: rgba(16, 24, 40, 0.5);
        border-radius: 20px;
        padding: 8px;
        gap: 8px;
        border: 1px solid rgba(0, 245, 255, 0.1);
        backdrop-filter: blur(10px);
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 14px;
        color: var(--text-secondary);
        font-weight: 500;
        padding: 10px 20px;
        transition: all 0.3s ease;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background: rgba(0, 245, 255, 0.05);
        color: var(--neon-cyan);
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, rgba(0, 245, 255, 0.15) 0%, rgba(255, 0, 170, 0.1) 100%) !important;
        border: 1px solid var(--neon-cyan) !important;
        color: var(--neon-cyan) !important;
        text-shadow: 0 0 15px rgba(0, 245, 255, 0.6);
        box-shadow: 0 0 20px rgba(0, 245, 255, 0.2);
    }
    
    /* === DATAFRAME - Matrix Style === */
    [data-testid="stDataFrame"] {
        border: 1px solid rgba(0, 245, 255, 0.15) !important;
        border-radius: 16px;
        background: rgba(10, 15, 28, 0.7);
        overflow: hidden;
    }
    
    [data-testid="stDataFrame"] th {
        background: rgba(0, 245, 255, 0.08) !important;
        color: var(--neon-cyan) !important;
        text-transform: uppercase;
        font-size: 0.7rem;
        letter-spacing: 1px;
    }
    
    [data-testid="stDataFrame"] tr:hover td {
        background: rgba(0, 245, 255, 0.05) !important;
    }
    
    /* === BUTTONS === */
    .stButton button {
        border-radius: 12px;
        font-weight: 600;
        transition: all 0.3s ease;
        border: 1px solid rgba(255, 255, 255, 0.1);
        background: rgba(255, 255, 255, 0.05);
    }
    
    .stButton button:hover {
        border-color: var(--neon-cyan);
        color: var(--neon-cyan);
        box-shadow: 0 0 20px rgba(0, 245, 255, 0.2);
        text-shadow: 0 0 10px rgba(0, 245, 255, 0.5);
    }
    
    /* === SIGNAL BADGES === */
    .signal-buy {
        background: linear-gradient(135deg, rgba(0, 255, 136, 0.2) 0%, rgba(0, 255, 136, 0.1) 100%);
        color: var(--neon-green);
        padding: 6px 16px;
        border-radius: 8px;
        font-weight: 700;
        border: 1px solid rgba(0, 255, 136, 0.3);
        text-shadow: 0 0 10px rgba(0, 255, 136, 0.5);
        animation: glow-green 2s ease-in-out infinite alternate;
    }
    
    .signal-sell, .signal-short {
        background: linear-gradient(135deg, rgba(255, 0, 170, 0.2) 0%, rgba(255, 0, 170, 0.1) 100%);
        color: var(--neon-pink);
        padding: 6px 16px;
        border-radius: 8px;
        font-weight: 700;
        border: 1px solid rgba(255, 0, 170, 0.3);
        text-shadow: 0 0 10px rgba(255, 0, 170, 0.5);
        animation: glow-pink 2s ease-in-out infinite alternate;
    }
    
    .signal-neutral {
        background: rgba(136, 146, 166, 0.1);
        color: var(--text-secondary);
        padding: 6px 16px;
        border-radius: 8px;
        font-weight: 600;
        border: 1px solid rgba(136, 146, 166, 0.2);
    }
    
    @keyframes glow-green {
        from { box-shadow: 0 0 5px rgba(0, 255, 136, 0.2); }
        to { box-shadow: 0 0 15px rgba(0, 255, 136, 0.4); }
    }
    
    @keyframes glow-pink {
        from { box-shadow: 0 0 5px rgba(255, 0, 170, 0.2); }
        to { box-shadow: 0 0 15px rgba(255, 0, 170, 0.4); }
    }
    
    /* === HERO P&L BANNER === */
    .hero-pnl {
        background: linear-gradient(135deg, #0a0f1c 0%, #1a1f2e 100%);
        border: 1px solid var(--border-glow);
        border-radius: 24px;
        padding: 40px;
        margin-bottom: 24px;
        position: relative;
        overflow: hidden;
    }
    
    .hero-pnl::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, var(--neon-cyan), var(--neon-pink), var(--neon-cyan));
        background-size: 200% 100%;
        animation: gradient-shift 3s ease infinite;
    }
    
    .hero-pnl::after {
        content: '';
        position: absolute;
        top: 0;
        right: 0;
        width: 300px;
        height: 300px;
        background: radial-gradient(circle, rgba(0, 245, 255, 0.1) 0%, transparent 70%);
        pointer-events: none;
    }
    
    @keyframes gradient-shift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    
    .hero-pnl .pnl-value {
        font-size: 4rem;
        font-weight: 700;
        background: linear-gradient(135deg, var(--neon-cyan) 0%, var(--neon-green) 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        text-shadow: 0 0 40px rgba(0, 245, 255, 0.3);
        margin: 0;
        line-height: 1.2;
    }
    
    .hero-pnl .pnl-value.negative {
        background: linear-gradient(135deg, var(--neon-pink) 0%, var(--neon-red) 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .hero-pnl .pnl-label {
        color: var(--text-secondary);
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-top: 8px;
    }
    
    /* === LIVE TICKER BANNER === */
    .ticker-banner {
        background: rgba(16, 24, 40, 0.6);
        border: 1px solid rgba(0, 245, 255, 0.1);
        border-radius: 12px;
        padding: 12px 20px;
        margin-bottom: 20px;
        overflow: hidden;
        position: relative;
    }
    
    .ticker-content {
        display: flex;
        gap: 40px;
        animation: ticker-scroll 30s linear infinite;
    }
    
    .ticker-item {
        display: flex;
        align-items: center;
        gap: 8px;
        white-space: nowrap;
    }
    
    .ticker-item.positive { color: var(--neon-green); }
    .ticker-item.negative { color: var(--neon-pink); }
    
    @keyframes ticker-scroll {
        0% { transform: translateX(0); }
        100% { transform: translateX(-50%); }
    }
    
    /* === STATUS INDICATOR === */
    .status-live {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(0, 255, 136, 0.1);
        border: 1px solid rgba(0, 255, 136, 0.3);
        padding: 8px 16px;
        border-radius: 20px;
        color: var(--neon-green);
        font-weight: 600;
    }
    
    .status-live::before {
        content: '';
        width: 8px;
        height: 8px;
        background: var(--neon-green);
        border-radius: 50%;
        animation: pulse 1.5s ease-in-out infinite;
    }
    
    .status-stopped {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(255, 68, 68, 0.1);
        border: 1px solid rgba(255, 68, 68, 0.3);
        padding: 8px 16px;
        border-radius: 20px;
        color: var(--neon-red);
        font-weight: 600;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.5; transform: scale(1.2); }
    }
    
    /* === POSITION CARDS === */
    .position-card {
        background: var(--bg-card);
        border: 1px solid rgba(0, 245, 255, 0.1);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 12px;
        transition: all 0.3s ease;
        position: relative;
    }
    
    .position-card:hover {
        border-color: var(--neon-cyan);
        transform: translateX(8px);
        box-shadow: -4px 0 20px rgba(0, 245, 255, 0.1);
    }
    
    .position-card.profit::before {
        content: '';
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 4px;
        background: var(--neon-green);
        border-radius: 4px 0 0 4px;
    }
    
    .position-card.loss::before {
        content: '';
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 4px;
        background: var(--neon-red);
        border-radius: 4px 0 0 4px;
    }
    
    /* === SCROLLBAR === */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: var(--bg-deep);
    }
    
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, var(--neon-cyan), var(--neon-pink));
        border-radius: 4px;
    }
    
    /* === EXPANDER === */
    .streamlit-expanderHeader {
        background: rgba(16, 24, 40, 0.5) !important;
        border: 1px solid rgba(0, 245, 255, 0.1) !important;
        border-radius: 12px !important;
        color: var(--text-primary) !important;
    }
    
    .streamlit-expanderHeader:hover {
        border-color: var(--neon-cyan) !important;
    }
    
    /* === SELECT BOX === */
    [data-baseweb="select"] {
        background: var(--bg-card) !important;
        border: 1px solid rgba(0, 245, 255, 0.2) !important;
        border-radius: 12px !important;
    }
    
    [data-baseweb="select"]:hover {
        border-color: var(--neon-cyan) !important;
    }
    
    /* === TEXT INPUT === */
    .stTextInput input, .stNumberInput input {
        background: var(--bg-card) !important;
        border: 1px solid rgba(0, 245, 255, 0.2) !important;
        border-radius: 12px !important;
        color: var(--text-primary) !important;
    }
    
    .stTextInput input:focus, .stNumberInput input:focus {
        border-color: var(--neon-cyan) !important;
        box-shadow: 0 0 15px rgba(0, 245, 255, 0.2) !important;
    }
</style>
""", unsafe_allow_html=True)

# Load Secrets (works on Streamlit Cloud and locally)
KEYS = {
    "t212": {
        "api": get_secret("T212_API_KEY"),
        "url": get_secret("T212_BASE_URL")
    },
    "capital": {
        "api": get_secret("CAPITAL_API_KEY"),
        "login": get_secret("CAPITAL_LOGIN"),
        "pass": get_secret("CAPITAL_PASSWORD"),
        "url": get_secret("CAPITAL_BASE_URL", "https://demo-api-capital.backend-capital.com")
    }
}

# --- State Management ---
# Using cache_resource to create a GLOBAL SINGLETON bot.
# This ensures that if you open the app on your phone, it sees the SAME bot as your computer.
# It also prevents multiple bots from running if you refresh the page.

@st.cache_resource(show_spinner=False)
def get_global_bot_instance(broker_code, api_key, base_url, login=None, password=None):
    """
    Create a persistent TradingBot instance that survives session refreshes
    and can be accessed from multiple devices (Singleton).
    """
    if broker_code == "t212":
        return TradingBot(api_key, base_url, broker="t212")
    else:
        return TradingBot(
            api_key, 
            base_url, 
            broker="capital", 
            cap_login=login, 
            cap_pass=password
        )

def get_or_create_bot(broker_code):
    """Retrieve the global bot instance."""
    if broker_code == "t212":
        if not KEYS['t212']['api']:
            st.error("Missing T212 Keys")
            return None
        return get_global_bot_instance(
            "t212", 
            KEYS['t212']['api'], 
            KEYS['t212']['url']
        )
    else:
        if not (KEYS['capital']['api'] and KEYS['capital']['login']):
            st.error("Missing Capital Keys")
            return None
        return get_global_bot_instance(
            "capital",
            KEYS['capital']['api'], 
            KEYS['capital']['url'], 
            KEYS['capital']['login'], 
            KEYS['capital']['pass']
        )

# --- Sidebar ---
# Logo and Branding
st.sidebar.markdown("""
<div style="text-align: center; padding: 20px 0 24px 0; border-bottom: 1px solid #2d3748; margin-bottom: 20px;">
    <div style="
        background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
        width: 60px;
        height: 60px;
        border-radius: 16px;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto 12px auto;
        font-size: 28px;
        box-shadow: 0 8px 20px rgba(59, 130, 246, 0.3);
    ">🤖</div>
    <h2 style="margin: 0; font-size: 1.3rem; font-weight: 700; color: #f8fafc;">TradingBot PRO</h2>
    <p style="margin: 4px 0 0 0; font-size: 0.75rem; color: #64748b;">AI Trading System v2.0</p>
</div>
""", unsafe_allow_html=True)

# Broker Selector with custom styling
st.sidebar.markdown('<p style="color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Select Broker</p>', unsafe_allow_html=True)
broker_mode = st.sidebar.radio("Active View", ["Capital.com (CFD)", "Trading 212 (Stocks)"], label_visibility="collapsed")
broker_code = "capital" if "Capital" in broker_mode else "t212"

current_bot = get_or_create_bot(broker_code)

if not current_bot:
    st.stop()

# Status Indicator with pulse animation
is_running = current_bot.is_running
status_class = "running" if is_running else "stopped"
status_text = "RUNNING" if is_running else "STOPPED"
pulse_class = "pulse" if is_running else ""

st.sidebar.markdown(f"""
<div style="margin: 20px 0;">
    <p style="color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Bot Status</p>
    <div class="status-badge {status_class}">
        <span class="{pulse_class}" style="
            width: 10px; 
            height: 10px; 
            border-radius: 50%; 
            background: {'#00d26a' if is_running else '#ff4757'};
            display: inline-block;
        "></span>
        {status_text}
    </div>
</div>
""", unsafe_allow_html=True)

# Control Buttons with custom styling
st.sidebar.markdown('<p style="color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Controls</p>', unsafe_allow_html=True)
c1, c2 = st.sidebar.columns(2)

# Custom button styles via markdown + actual buttons
with c1:
    if st.button("▶ START", key=f"start_{broker_code}", use_container_width=True):
        current_bot.start_loop()
        st.rerun()

with c2:
    if st.button("⏹ STOP", key=f"stop_{broker_code}", use_container_width=True):
        current_bot.stop_loop()
        st.rerun()

st.sidebar.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)
st.sidebar.divider()

# --- Settings (Persistent per broker) ---
st.sidebar.markdown(f"""
<p style="color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px;">
    ⚙️ {broker_code.upper()} SETTINGS
</p>
""", unsafe_allow_html=True)

# 1. Trade Amount
curr_label = "USD" if broker_code == "capital" else "CZK"
# For small accounts (~$85 / 2000 CZK): Risk max 5% per trade = ~$4
# This allows ~20 trades before account is depleted (risk management)
default_amt = 4.0 if broker_code == "capital" else 100.0

# Use session state to persist value without reset
risk_key = f"risk_{broker_code}"
if risk_key not in st.session_state:
    st.session_state[risk_key] = default_amt

amount = st.sidebar.number_input(
    f"💵 Trade Amount ({curr_label})", 
    key=risk_key, 
    min_value=1.0, 
    step=1.0,
    help="Target value of the position in account currency."
)
current_bot.trade_amount = amount

# Small Account Mode toggle
if broker_code == "capital":
    small_account = st.sidebar.checkbox(
        "💰 Small Account Mode",
        value=getattr(current_bot, 'small_account_mode', True),
        help="Under $200 capital - trades curated list of 35+ low-margin instruments"
    )
    current_bot.small_account_mode = small_account
    
    if small_account:
        st.sidebar.success("📊 Trading 35+ curated instruments (low margin requirements)")

# 2. Market Categories (Capital Only)
if broker_code == "capital":
    # Market Scan Scope with custom header
    st.sidebar.markdown("""
    <p style="color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; margin: 16px 0 8px 0;">
        🌍 Market Scan Scope
    </p>
    """, unsafe_allow_html=True)
    
    available_cats = ["Forex", "Indices", "Commodities", "Crypto", "US Stocks"]
    
    # Source of Truth: The Bot's internal state
    current_active = getattr(current_bot, 'active_categories', available_cats)
    
    selected_cats = st.sidebar.multiselect(
        "Active Categories",
        available_cats,
        default=current_active,
        label_visibility="collapsed"
    )
    
    # Apply to bot
    if set(selected_cats) != set(current_active):
        current_bot.set_active_categories(selected_cats)

    # Daily limits (scalping: protect capital, lock profit)
    st.sidebar.markdown("""
    <p style="color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; margin: 16px 0 8px 0;">
        🛡️ Risk Management
    </p>
    """, unsafe_allow_html=True)
    
    # Max Positions slider
    from bot import MAX_POSITIONS as DEFAULT_MAX_POS
    max_pos = st.sidebar.slider(
        "Max open positions",
        min_value=1, max_value=10, 
        value=getattr(current_bot, 'max_positions', DEFAULT_MAX_POS),
        key=f"max_pos_{broker_code}",
        help="Maximum number of trades open at the same time"
    )
    current_bot.max_positions = max_pos
    
    max_loss = st.sidebar.number_input(
        "Max daily loss (stop trading)", 
        value=getattr(current_bot, 'max_daily_loss', 50.0), 
        min_value=0.0, step=5.0, key=f"max_loss_{broker_code}",
        help="Stop opening new trades when today's loss reaches this."
    )
    profit_target = st.sidebar.number_input(
        "Daily profit target (optional)", 
        value=getattr(current_bot, 'daily_profit_target', 30.0), 
        min_value=0.0, step=5.0, key=f"profit_tgt_{broker_code}",
        help="Stop opening new trades when today's profit reaches this."
    )
    current_bot.max_daily_loss = max_loss
    current_bot.daily_profit_target = profit_target

    # Strategy Controls
    with st.sidebar.expander("🎯 Strategy Settings", expanded=False):
        cfg = getattr(current_bot, 'strategy_config', {})

        st.markdown('<p style="color: #3b82f6; font-weight: 600; margin-bottom: 8px;">Entry Filters</p>', unsafe_allow_html=True)
        enable_shorts = st.checkbox("Enable SHORT trades", value=cfg.get('enable_shorts', True))
        require_session = st.checkbox("Session filter (London/NY only)", value=cfg.get('require_session', True))
        require_volume = st.checkbox("Volume confirmation", value=cfg.get('require_volume', True))

        st.markdown('<p style="color: #00d26a; font-weight: 600; margin: 16px 0 8px 0;">LONG Parameters</p>', unsafe_allow_html=True)
        new_rsi_buy = st.slider("RSI Max (Buy)", 50, 80, cfg.get('rsi_buy', 58))
        new_rsi_low = st.slider("RSI Oversold", 20, 50, cfg.get('rsi_oversold', 38))

        st.markdown('<p style="color: #ff4757; font-weight: 600; margin: 16px 0 8px 0;">SHORT Parameters</p>', unsafe_allow_html=True)
        new_rsi_sell = st.slider("RSI Min (Sell)", 30, 60, cfg.get('rsi_sell', 42))
        new_rsi_high = st.slider("RSI Overbought", 55, 85, cfg.get('rsi_overbought', 62))

        st.markdown('<p style="color: #8b5cf6; font-weight: 600; margin: 16px 0 8px 0;">General</p>', unsafe_allow_html=True)
        new_adx = st.slider("Min Trend ADX", 10, 50, cfg.get('adx_min', 28))
        risk_reward = st.slider("Risk:Reward (TP/SL)", 1.2, 3.0, cfg.get('risk_reward', 1.8), step=0.1)
        atr_mult = st.slider("ATR SL multiplier", 1.0, 2.5, cfg.get('atr_sl_mult', 1.5), step=0.1)

        if not hasattr(current_bot, 'strategy_config'):
             current_bot.strategy_config = {}
        current_bot.strategy_config.update({
            'rsi_buy': new_rsi_buy,
            'rsi_oversold': new_rsi_low,
            'rsi_sell': new_rsi_sell,
            'rsi_overbought': new_rsi_high,
            'adx_min': new_adx,
            'risk_reward': risk_reward,
            'atr_sl_mult': atr_mult,
            'enable_shorts': enable_shorts,
            'require_session': require_session,
            'require_volume': require_volume
        })

    # Backtest Results Info
    with st.sidebar.expander("📊 Backtest Results", expanded=False):
        st.markdown("""
        <div style="font-size: 0.8rem;">
            <p style="color: #00d26a; margin: 8px 0 4px 0; font-weight: 600;">✅ Doporučené trhy:</p>
            <ul style="color: #94a3b8; margin: 0; padding-left: 16px;">
                <li>AUDUSD (PF: 3.36)</li>
                <li>ETH-USD (PF: 1.95)</li>
                <li>EURUSD (PF: 2.02)</li>
                <li>USDJPY (PF: 1.12)</li>
                <li>Silver (PF: 1.19)</li>
            </ul>
            <p style="color: #ff4757; margin: 12px 0 4px 0; font-weight: 600;">❌ Vyloučené trhy:</p>
            <ul style="color: #94a3b8; margin: 0; padding-left: 16px;">
                <li>BTC (nestabilní)</li>
                <li>GBPUSD (ztrátový)</li>
                <li>Gold (ztrátový)</li>
            </ul>
            <p style="color: #64748b; margin-top: 12px; font-size: 0.7rem;">
                Výsledky z backtestů únor 2026<br>
                1 měsíc, 5min interval
            </p>
        </div>
        """, unsafe_allow_html=True)

    st.sidebar.divider()

# Footer info
st.sidebar.markdown("""
<div style="
    background: linear-gradient(145deg, #1e2530 0%, #252d3a 100%);
    border: 1px solid #2d3748;
    border-radius: 10px;
    padding: 12px;
    margin-top: 8px;
">
    <p style="color: #64748b; font-size: 0.75rem; margin: 0; text-align: center;">
        🧠 Strategy: Mean Reversion<br>
        📊 Win Rate: 56% | Assets: 30
    </p>
</div>
""", unsafe_allow_html=True)

# --- Main Dashboard ---
# Custom Header with gradient
st.markdown(f"""
<div style="margin-bottom: 24px;">
    <h1 style="
        background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        font-weight: 800;
        margin: 0;
    ">{broker_mode}</h1>
    <p style="color: #64748b; margin-top: 4px;">Real-time trading dashboard</p>
</div>
""", unsafe_allow_html=True)

# Helper function for custom metric cards
def render_metric_card(icon, label, value, subtitle="", color_class=""):
    """Render a custom styled metric card."""
    value_class = f"value {color_class}" if color_class else "value"
    return f"""
    <div class="metric-card">
        <div class="icon">{icon}</div>
        <div class="label">{label}</div>
        <div class="{value_class}">{value}</div>
        {f'<div style="color: #64748b; font-size: 0.75rem; margin-top: 4px;">{subtitle}</div>' if subtitle else ''}
    </div>
    """

# 1. LIVE METRICS (Fragment)
@st.fragment(run_every=2)
def show_metrics():
    cash = 0
    value = 0
    pos_count = 0
    
    try:
        # FAST PATH: Read from Bot Cache (if running)
        if current_bot.is_running and hasattr(current_bot, 'cached_account') and current_bot.cached_account:
            data = current_bot.cached_account
            if broker_code == "t212":
                cash = data.get('free', 0)
                value = data.get('total', 0)
            else:
                # Capital
                if 'accounts' in data:
                    acc = data['accounts'][0]
                    cash = acc.get('balance', {}).get('available', 0)
                    value = acc.get('balance', {}).get('total', 0)
            
            # Positions Cache
            raw_pos = getattr(current_bot, 'cached_positions', [])
            pos_count = len(raw_pos)

        # SLOW PATH: Manual Fetch (Bot stopped or initializing)
        else:
            if broker_code == "t212":
                c = current_bot.client.get_account_cash()
                if c: 
                    cash = c.get('free', 0)
                    value = c.get('total', 0)
            else:
                info = current_bot.client.get_account_info()
                if info and 'accounts' in info:
                    acc = info['accounts'][0]
                    cash = acc.get('balance', {}).get('available', 0)
                    value = acc.get('balance', {}).get('total', 0)
            
            raw_pos = current_bot.client.get_positions()
            pos_count = len(raw_pos) if raw_pos else 0
        
    except Exception as e:
        pass
    
    # Daily PnL
    daily_pnl = getattr(current_bot, 'daily_pnl', 0)
    pnl_color = "positive" if daily_pnl >= 0 else "negative"
    
    # Render custom metric cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(render_metric_card(
            "💰", "Available Cash", 
            f"{cash:,.2f} {curr_label}",
            "Ready to trade"
        ), unsafe_allow_html=True)
    
    with col2:
        st.markdown(render_metric_card(
            "📊", "Total Equity", 
            f"{value:,.2f} {curr_label}",
            "Cash + Open P&L"
        ), unsafe_allow_html=True)
    
    with col3:
        st.markdown(render_metric_card(
            "📈", "Open Positions", 
            str(pos_count),
            "Active trades"
        ), unsafe_allow_html=True)
    
    with col4:
        st.markdown(render_metric_card(
            "💹", "Today's P&L", 
            f"${daily_pnl:+.2f}",
            "Daily performance",
            pnl_color
        ), unsafe_allow_html=True)

    # --- SMART SENTIMENT PANEL (NEW) ---
    st.markdown("### 🧠 Smart Sentiment Analysis")
    
    # Get sentiment data
    if hasattr(current_bot, 'smart_analyst'):
        try:
            is_safe, msg = current_bot.smart_analyst.get_market_sentiment()
        except:
            is_safe, msg = True, "Initializing..."
        
        s_col1, s_col2 = st.columns([1, 2])
        
        with s_col1:
            # VIX Gauge equivalent
            sentiment_color = "#00d26a" if is_safe else "#ff4757"
            sentiment_icon = "😌" if is_safe else "😱"
            st.markdown(f"""
            <div style="
                background: linear-gradient(145deg, #1e2530 0%, {sentiment_color}20 100%);
                border: 1px solid {sentiment_color}40;
                border-radius: 12px;
                padding: 16px;
                text-align: center;
            ">
                <div style="font-size: 2.5rem; margin-bottom: 8px;">{sentiment_icon}</div>
                <div style="color: {sentiment_color}; font-weight: 700; font-size: 1.2rem;">
                    {msg}
                </div>
                <div style="color: #94a3b8; font-size: 0.8rem; margin-top: 4px;">Global Market Sentiment</div>
            </div>
            """, unsafe_allow_html=True)
            
        with s_col2:
            st.info("""
            **Smart Analyza Aktiv:**
            - 📊 **Analyst Check**: Yahoo Finance doporučení (Buy/Sell).
            - 🌍 **Global Filter**: Pokud VIX > 25 (Panika), nákupy jsou pozastaveny.
            - 🔎 **Discovery**: Aktivně vyhledává nové příležitosti s ratingem "Strong Buy".
            """)
    
    st.divider()
    
    # Session status alerts
    reason = getattr(current_bot, 'session_stopped_reason', None)
    if reason == "daily_loss":
        st.markdown("""
        <div style="background: rgba(255, 71, 87, 0.15); border: 1px solid rgba(255, 71, 87, 0.3); 
                    border-radius: 10px; padding: 12px 16px; margin-top: 16px; color: #ff4757;">
            ⚠️ Session stopped: Daily loss limit reached
        </div>
        """, unsafe_allow_html=True)
    elif reason == "profit_target":
        st.markdown("""
        <div style="background: rgba(0, 210, 106, 0.15); border: 1px solid rgba(0, 210, 106, 0.3); 
                    border-radius: 10px; padding: 12px 16px; margin-top: 16px; color: #00d26a;">
            🎯 Session stopped: Daily profit target reached!
        </div>
        """, unsafe_allow_html=True)

show_metrics()

# Tabs
tabs = st.tabs(["🧠 AI Scanner", "📊 Positions", "📈 Market Chart", "🏆 Performance", "🔬 Backtest", "🎯 Strategy Intelligence", "🤖 Learning", "📅 Calendar"])

# TAB 1: AI SCANNER (Live Data + Logs)
with tabs[0]:
    @st.fragment(run_every=1)
    def show_scanner():
        # Header with scan stats
        results = getattr(current_bot, 'scan_results', [])
        
        # Quick stats
        if results:
            buy_signals = len([r for r in results if r.get('Action') == 'BUY'])
            sell_signals = len([r for r in results if r.get('Action') == 'SELL'])
            neutral_signals = len([r for r in results if r.get('Action') == 'NEUTRAL'])
            
            st.markdown(f"""
            <div style="display: flex; gap: 16px; margin-bottom: 20px;">
                <div style="background: rgba(0, 210, 106, 0.1); border: 1px solid rgba(0, 210, 106, 0.2); border-radius: 8px; padding: 12px 20px; flex: 1; text-align: center;">
                    <div style="color: #00d26a; font-size: 1.5rem; font-weight: 700;">{buy_signals}</div>
                    <div style="color: #64748b; font-size: 0.75rem; text-transform: uppercase;">Buy Signals</div>
                </div>
                <div style="background: rgba(255, 71, 87, 0.1); border: 1px solid rgba(255, 71, 87, 0.2); border-radius: 8px; padding: 12px 20px; flex: 1; text-align: center;">
                    <div style="color: #ff4757; font-size: 1.5rem; font-weight: 700;">{sell_signals}</div>
                    <div style="color: #64748b; font-size: 0.75rem; text-transform: uppercase;">Sell Signals</div>
                </div>
                <div style="background: rgba(148, 163, 184, 0.1); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 8px; padding: 12px 20px; flex: 1; text-align: center;">
                    <div style="color: #94a3b8; font-size: 1.5rem; font-weight: 700;">{neutral_signals}</div>
                    <div style="color: #64748b; font-size: 0.75rem; text-transform: uppercase;">Neutral</div>
                </div>
                <div style="background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.2); border-radius: 8px; padding: 12px 20px; flex: 1; text-align: center;">
                    <div style="color: #3b82f6; font-size: 1.5rem; font-weight: 700;">{len(results)}</div>
                    <div style="color: #64748b; font-size: 0.75rem; text-transform: uppercase;">Total Scanned</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # Scan Results Table
        st.markdown('<p style="color: #f8fafc; font-weight: 600; margin-bottom: 12px;">📡 Live Strategy Decisions</p>', unsafe_allow_html=True)
        
        if results:
            # Use pandas dataframe with Streamlit styling
            df_scan = pd.DataFrame(results[-50:])
            
            # Reorder and select columns
            cols = ["Time", "Ticker", "Action", "RSI", "Reason", "Price"]
            cols = [c for c in cols if c in df_scan.columns]
            
            if cols:
                df_display = df_scan[cols].copy()
                
                # Style the dataframe
                def color_action(val):
                    if val == 'BUY':
                        return 'background-color: rgba(0, 210, 106, 0.2); color: #00d26a; font-weight: bold'
                    elif val == 'SELL':
                        return 'background-color: rgba(255, 71, 87, 0.2); color: #ff4757; font-weight: bold'
                    return 'color: #94a3b8'
                
                def color_rsi(val):
                    try:
                        v = float(val)
                        if v < 30:
                            return 'color: #00d26a; font-weight: bold'
                        elif v > 70:
                            return 'color: #ff4757; font-weight: bold'
                    except:
                        pass
                    return 'color: #94a3b8'
                
                styled_df = df_display.style.map(
                    color_action, subset=['Action']
                ).map(
                    color_rsi, subset=['RSI']
                )
                
                st.dataframe(
                    styled_df,
                    width="stretch",
                    height=280,
                    hide_index=True
                )
            else:
                st.dataframe(df_scan, width="stretch", height=280, hide_index=True)
        else:
            st.markdown("""
            <div style="
                background: linear-gradient(145deg, #1e2530 0%, #252d3a 100%);
                border: 1px solid #2d3748;
                border-radius: 12px;
                padding: 40px;
                text-align: center;
            ">
                <div style="font-size: 3rem; margin-bottom: 12px;">🔍</div>
                <p style="color: #f8fafc; font-weight: 500; margin: 0;">Scanner is warming up...</p>
                <p style="color: #64748b; font-size: 0.85rem; margin-top: 4px;">Start the bot to begin scanning markets</p>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)
        
        # System Logs with terminal styling
        st.markdown('<p style="color: #f8fafc; font-weight: 600; margin-bottom: 12px;">💻 System Logs</p>', unsafe_allow_html=True)
        
        logs = list(current_bot.log_messages)
        if logs:
            # Build terminal-style log output
            log_html = ""
            for msg in reversed(logs[-30:]):
                # Colorize based on content
                if "BUY" in msg or "✅" in msg or "CONFIRMED" in msg:
                    log_color = "#00d26a"
                elif "SELL" in msg or "SHORT" in msg:
                    log_color = "#ff4757"
                elif "ERROR" in msg or "❌" in msg or "REJECTED" in msg:
                    log_color = "#ff4757"
                elif "WARNING" in msg or "Skipped" in msg:
                    log_color = "#fbbf24"
                else:
                    log_color = "#00d26a"
                
                log_html += f'<div style="color: {log_color}; border-bottom: 1px solid #1a1f2e; padding: 4px 0;">{msg}</div>'
            
            st.markdown(f"""
            <div style="
                background: #0a0d12;
                border: 1px solid #2d3748;
                border-radius: 8px;
                padding: 16px;
                font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
                font-size: 0.8rem;
                max-height: 250px;
                overflow-y: auto;
            ">
                {log_html}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="
                background: #0a0d12;
                border: 1px solid #2d3748;
                border-radius: 8px;
                padding: 20px;
                text-align: center;
                color: #64748b;
                font-family: monospace;
            ">
                Waiting for logs...
            </div>
            """, unsafe_allow_html=True)
    
    show_scanner()

# TAB 2: POSITIONS
with tabs[1]:
    @st.fragment(run_every=2)
    def show_positions():
        positions = []
        try:
            positions = current_bot.client.get_positions()
            if not isinstance(positions, list):
                positions = []
        except Exception:
            positions = []
        
        # Store positions for chart tab
        if 'open_positions' not in st.session_state:
            st.session_state.open_positions = []
        st.session_state.open_positions = positions
        
        if positions:
            # Use pandas DataFrame instead of HTML
            data = []
            for p in positions:
                try:
                    if not isinstance(p, dict):
                        continue
                    if broker_code == 'capital':
                        mkt = p.get('market', {}) or {}
                        pos = p.get('position', {}) or {}
                        data.append({
                            "Symbol": mkt.get('epic') or pos.get('epic', 'N/A'),
                            "Size": pos.get('size', 0),
                            "Direction": pos.get('direction', 'N/A'),
                            "P&L": float(pos.get('upl', 0) or 0),
                            "Entry": pos.get('level', 0),
                            "Current": mkt.get('bid', 0)
                        })
                    else:
                        data.append({
                            "Symbol": p.get('ticker', 'N/A'),
                            "Size": p.get('quantity', 0),
                            "Direction": 'BUY',
                            "P&L": float(p.get('ppl', 0) or 0),
                            "Entry": p.get('averagePrice', 0)
                        })
                except Exception:
                    continue
            
            if data:
                df = pd.DataFrame(data)
                
                # Style function for P&L
                def style_pnl(val):
                    try:
                        if float(val) >= 0:
                            return 'color: #00d26a; font-weight: bold'
                        return 'color: #ff4757; font-weight: bold'
                    except:
                        return ''
                
                def style_direction(val):
                    if val == 'BUY':
                        return 'background-color: rgba(0, 210, 106, 0.2); color: #00d26a'
                    return 'background-color: rgba(255, 71, 87, 0.2); color: #ff4757'
                
                styled = df.style.map(style_pnl, subset=['P&L']).map(style_direction, subset=['Direction'])
                
                # Summary metrics
                total_pnl = sum(d['P&L'] for d in data)
                winning = len([d for d in data if d['P&L'] > 0])
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Open Positions", len(data))
                col2.metric("Unrealized P&L", f"${total_pnl:+.2f}", delta="Profit" if total_pnl > 0 else "Loss")
                col3.metric("Winning", f"{winning}/{len(data)}")
                
                st.dataframe(styled, width="stretch", hide_index=True)
            else:
                st.info("No valid position data")
        else:
            st.info("No open trades. Waiting for signals...")

    show_positions()

# TAB 4: PERFORMANCE
with tabs[3]:
    @st.fragment(run_every=30)
    def show_performance():
        st.subheader("Daily Performance Report")
        st.caption("Last 48 hours trading activity from Capital.com")
        
        try:
            if current_bot.broker == "capital":
                # Fetch history from Capital.com
                history = current_bot.client.get_history(last_hours=48)  # 48h for more data
                
                # Filter valid trades
                trades = []
                for t in (history or []):
                    if isinstance(t, dict) and t.get('profitAndLoss') is not None:
                        try:
                            pnl = float(t.get('profitAndLoss', 0))
                            if pnl != 0:
                                trades.append(t)
                        except:
                            pass
                
                if trades:
                    total_pnl = sum(float(t.get('profitAndLoss', 0)) for t in trades)
                    total_trades = len(trades)
                    wins = len([t for t in trades if float(t.get('profitAndLoss', 0)) > 0])
                    losses = total_trades - wins
                    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
                    
                    winning_pnls = [float(t.get('profitAndLoss', 0)) for t in trades if float(t.get('profitAndLoss', 0)) > 0]
                    losing_pnls = [float(t.get('profitAndLoss', 0)) for t in trades if float(t.get('profitAndLoss', 0)) < 0]
                    
                    avg_win = sum(winning_pnls) / len(winning_pnls) if winning_pnls else 0
                    avg_loss = sum(losing_pnls) / len(losing_pnls) if losing_pnls else 0
                    profit_factor = abs(sum(winning_pnls) / sum(losing_pnls)) if losing_pnls and sum(losing_pnls) != 0 else 0
                    
                    # KPI Metrics using st.metric
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Daily P&L", f"${total_pnl:+.2f}", delta="Profit" if total_pnl > 0 else "Loss")
                    col2.metric("Win Rate", f"{win_rate:.1f}%", delta="Good" if win_rate >= 50 else "Low")
                    col3.metric("Profit Factor", f"{profit_factor:.2f}", delta="Profitable" if profit_factor > 1 else "Losing")
                    col4.metric("Total Trades", total_trades)
                    
                    st.divider()
                    
                    # Secondary metrics
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Winning Trades", wins)
                    col2.metric("Losing Trades", losses)
                    col3.metric("Avg Win", f"${avg_win:+.2f}")
                    col4.metric("Avg Loss", f"${avg_loss:.2f}")
                    
                    # Win rate progress bar
                    if total_trades > 0:
                        st.progress(wins / total_trades, text=f"Win Rate: {wins}/{total_trades}")
                    
                    st.divider()
                    
                    # Trade history table using pandas
                    st.subheader("Trade History")
                    trade_data = []
                    for t in trades[:30]:
                        pnl = float(t.get('profitAndLoss', 0))
                        trade_data.append({
                            "Date": str(t.get('date', 'N/A'))[:19],
                            "Market": t.get('epic', t.get('instrumentName', 'N/A')),
                            "Type": t.get('type', 'N/A'),
                            "P&L": pnl
                        })
                    
                    if trade_data:
                        df = pd.DataFrame(trade_data)
                        
                        def style_pnl(val):
                            try:
                                if float(val) >= 0:
                                    return 'color: #00d26a; font-weight: bold'
                                return 'color: #ff4757; font-weight: bold'
                            except:
                                return ''
                        
                        styled = df.style.map(style_pnl, subset=['P&L'])
                        st.dataframe(styled, width="stretch", hide_index=True)
                else:
                    st.info("No closed trades in the last 48 hours. Start trading to see performance data.")
                    
                    # Show account info instead
                    try:
                        acc = current_bot.client.get_account_info()
                        if acc and 'accounts' in acc and acc['accounts']:
                            account = acc['accounts'][0]
                            balance = account.get('balance', {})
                            
                            st.subheader("Account Overview")
                            col1, col2, col3 = st.columns(3)
                            col1.metric("Balance", f"${balance.get('balance', 0):.2f}")
                            col2.metric("Available", f"${balance.get('available', 0):.2f}")
                            col3.metric("P&L", f"${balance.get('profitLoss', 0):.2f}")
                    except:
                        pass
            else:
                st.info("Performance data only available for Capital.com. Switch broker to view.")
        except Exception as e:
            st.warning(f"Could not load performance data. Error: {str(e)[:100]}")

    show_performance()


# TAB 3: CHART (Static - No Reload)
with tabs[2]:
    st.subheader("Market Chart")
    
    # Get open positions for chart selection
    position_symbols = []
    try:
        positions = current_bot.client.get_positions()
        if isinstance(positions, list):
            for p in positions:
                if isinstance(p, dict):
                    if broker_code == 'capital':
                        mkt = p.get('market', {}) or {}
                        pos = p.get('position', {}) or {}
                        symbol = mkt.get('epic') or pos.get('epic')
                        if symbol:
                            position_symbols.append(symbol)
                    else:
                        ticker = p.get('ticker')
                        if ticker:
                            position_symbols.append(ticker)
    except:
        pass
    
    # Build watchlist - prioritize open positions
    watch = []
    
    if position_symbols:
        st.success(f"You have {len(position_symbols)} open position(s)")
        watch = position_symbols.copy()
    
    # Add priority tickers as fallback
    priority_tickers = ["EURUSD", "AUDUSD", "ETHUSD", "USDJPY"]
    for pt in priority_tickers:
        if pt not in watch:
            watch.append(pt)
    
    if not watch:
        watch = ["EURUSD", "GBPUSD", "BTCUSD"]
    
    # Selector
    selected_ticker = st.selectbox(
        "Select Market to View", 
        watch, 
        key=f"chart_sel_{broker_code}",
        help="Open positions are shown first"
    )
    
    # Show if this is an open position
    if selected_ticker in position_symbols:
        st.info(f"📊 Viewing open position: {selected_ticker}")
    
    # TradingView Embed
    import streamlit.components.v1 as components
    
    # Helper for symbol map (Capital epic -> TradingView symbol)
    def get_tv_symbol(epic):
        # Map common Capital.com epics to TradingView symbols
        map_dict = {
            'EURUSD': 'FX:EURUSD',
            'GBPUSD': 'FX:GBPUSD',
            'AUDUSD': 'FX:AUDUSD',
            'USDJPY': 'FX:USDJPY',
            'ETHUSD': 'COINBASE:ETHUSD',
            'BTCUSD': 'COINBASE:BTCUSD',
            'Gold': 'TVC:GOLD',
            'Silver': 'TVC:SILVER',
            'US500': 'FOREXCOM:SPXUSD',
            'US30': 'FOREXCOM:DJI',
            '^NDX': 'NASDAQ:NDX',
            '^GSPC': 'AMEX:SPY',
            'GC=F': 'TVC:GOLD',
            'BTC-USD': 'COINBASE:BTCUSD',
            'ETH-USD': 'COINBASE:ETHUSD',
        }
        
        # Direct match
        if epic in map_dict:
            return map_dict[epic]
        
        # Forex pairs (6 letter codes like EURUSD)
        if len(epic) == 6 and epic.isalpha():
            return f"FX:{epic}"
        
        # Yahoo format
        if epic.endswith("=X"):
            return f"FX:{epic.replace('=X','')}"
        if epic.endswith("-USD"):
            coin = epic.replace("-USD", "")
            return f"COINBASE:{coin}USD"
        
        # Default - try as FX
        return f"FX:{epic}"

    tv_symbol = get_tv_symbol(selected_ticker)

    # Dark theme TradingView chart
    tv_html = f"""
    <div class="tradingview-widget-container" style="border-radius: 12px; overflow: hidden; border: 1px solid #2d3748;">
      <div id="tradingview_chart"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
        "width": "100%", 
        "height": 520, 
        "symbol": "{tv_symbol}", 
        "interval": "5",
        "timezone": "Etc/UTC", 
        "theme": "dark", 
        "style": "1", 
        "locale": "en",
        "toolbar_bg": "#1e2530", 
        "enable_publishing": false, 
        "container_id": "tradingview_chart",
        "studies": ["RSI@tv-basicstudies", "MAExp@tv-basicstudies"],
        "hide_side_toolbar": false,
        "allow_symbol_change": true,
        "save_image": false,
        "backgroundColor": "#0f1419"
      }}
      );
      </script>
    </div>
    """
    components.html(tv_html, height=530)

# TAB 5: BACKTEST
with tabs[4]:
    st.markdown("""
    <div style="margin-bottom: 20px;">
        <h3 style="color: #f8fafc; margin: 0;">🔬 Strategy Backtesting</h3>
        <p style="color: #64748b; font-size: 0.9rem; margin-top: 4px;">Test your strategy on historical data before live trading</p>
    </div>
    """, unsafe_allow_html=True)

    # Backtest Controls
    col1, col2, col3 = st.columns([2, 1, 1])

    # Ticker Selection
    default_tickers = ["EURUSD=X", "GBPUSD=X", "BTC-USD", "ETH-USD", "GC=F", "^NDX", "AAPL", "TSLA"]
    if broker_code == "capital" and hasattr(current_bot, 'market_categories'):
        dynamic_tickers = []
        for cat, items in current_bot.market_categories.items():
            for i in items[:5]:  # Limit per category
                dynamic_tickers.append(i['yf'])
        if dynamic_tickers:
            default_tickers = list(set(dynamic_tickers + default_tickers[:4]))

    with col1:
        bt_ticker = st.selectbox("Select Ticker", default_tickers, key="bt_ticker")

    with col2:
        bt_period = st.selectbox("Period", ["1mo", "3mo", "6mo"], index=1, key="bt_period")

    with col3:
        bt_interval = st.selectbox("Interval", ["5m", "15m", "1h"], index=0, key="bt_interval")

    # Strategy Config for Backtest (use current bot config)
    with st.expander("Strategy Parameters (for backtest)"):
        bt_cfg = current_bot.strategy_config.copy() if hasattr(current_bot, 'strategy_config') else {}

        col_a, col_b = st.columns(2)
        with col_a:
            bt_enable_shorts = st.checkbox("Enable SHORTs", value=bt_cfg.get('enable_shorts', True), key="bt_shorts")
            bt_rsi = st.slider("RSI Max (Buy)", 50, 75, bt_cfg.get('rsi_buy', 58), key="bt_rsi")
            bt_rsi_low = st.slider("RSI Oversold", 25, 45, bt_cfg.get('rsi_oversold', 38), key="bt_rsi_low")
        with col_b:
            bt_require_vol = st.checkbox("Volume filter", value=False, key="bt_vol")
            bt_rsi_sell = st.slider("RSI Min (Sell)", 30, 60, bt_cfg.get('rsi_sell', 42), key="bt_rsi_sell")
            bt_rsi_high = st.slider("RSI Overbought", 55, 85, bt_cfg.get('rsi_overbought', 62), key="bt_rsi_high")

        bt_adx = st.slider("Min ADX", 15, 40, bt_cfg.get('adx_min', 28), key="bt_adx")
        bt_rr = st.slider("Risk:Reward", 1.2, 3.0, bt_cfg.get('risk_reward', 1.8), step=0.1, key="bt_rr")
        bt_atr = st.slider("ATR SL Mult", 1.0, 2.5, bt_cfg.get('atr_sl_mult', 1.5), step=0.1, key="bt_atr")

    # Run Backtest Button
    if st.button("Run Backtest", type="primary", key="run_bt"):
        with st.spinner(f"Running backtest on {bt_ticker}..."):
            bt_config = {
                "rsi_buy": bt_rsi,
                "rsi_oversold": bt_rsi_low,
                "rsi_sell": bt_rsi_sell,
                "rsi_overbought": bt_rsi_high,
                "adx_min": bt_adx,
                "risk_reward": bt_rr,
                "atr_sl_mult": bt_atr,
                "max_risk_pct": 0.006,
                "require_volume": bt_require_vol,
                "require_session": False,  # Disable for backtest
                "enable_shorts": bt_enable_shorts
            }

            backtester = Backtester(strategy_config=bt_config)
            result = backtester.run(bt_ticker, period=bt_period, interval=bt_interval)

            # Store in session state
            st.session_state['bt_result'] = result

    # Display Results
    if 'bt_result' in st.session_state:
        result = st.session_state['bt_result']

        if 'error' in result:
            st.markdown(f"""
            <div style="background: rgba(255, 71, 87, 0.1); border: 1px solid rgba(255, 71, 87, 0.3); 
                        border-radius: 10px; padding: 16px; color: #ff4757;">
                ❌ Backtest failed: {result['error']}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown('<div style="height: 20px;"></div>', unsafe_allow_html=True)

            # KPI Cards for Backtest Results
            wr = result.get('win_rate', 0)
            pf = result.get('profit_factor', 0)
            tr = result.get('total_return_pct', 0)
            dd = result.get('max_drawdown_pct', 0)
            
            wr_class = "success" if wr >= 50 else "warning" if wr >= 40 else "danger"
            pf_class = "success" if pf >= 1.5 else "warning" if pf >= 1 else "danger"
            tr_class = "success" if tr > 0 else "danger"
            
            st.markdown(f"""
            <div class="kpi-grid">
                <div class="kpi-card {wr_class}">
                    <div class="kpi-value">{wr}%</div>
                    <div class="kpi-label">Win Rate</div>
                </div>
                <div class="kpi-card {pf_class}">
                    <div class="kpi-value">{pf}</div>
                    <div class="kpi-label">Profit Factor</div>
                </div>
                <div class="kpi-card danger">
                    <div class="kpi-value">-{dd}%</div>
                    <div class="kpi-label">Max Drawdown</div>
                </div>
                <div class="kpi-card {tr_class}">
                    <div class="kpi-value">{tr:+.2f}%</div>
                    <div class="kpi-label">Total Return</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown('<div style="height: 16px;"></div>', unsafe_allow_html=True)
            
            # Second row
            st.markdown(f"""
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px;">
                <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 10px; padding: 16px; text-align: center;">
                    <div style="color: #3b82f6; font-size: 1.2rem; font-weight: 600;">{result.get('total_trades', 0)}</div>
                    <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">Total Trades</div>
                </div>
                <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 10px; padding: 16px; text-align: center;">
                    <div style="color: #00d26a; font-size: 1.2rem; font-weight: 600;">+{result.get('avg_win_pct', 0)}%</div>
                    <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">Avg Win</div>
                </div>
                <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 10px; padding: 16px; text-align: center;">
                    <div style="color: #ff4757; font-size: 1.2rem; font-weight: 600;">{result.get('avg_loss_pct', 0)}%</div>
                    <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">Avg Loss</div>
                </div>
                <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 10px; padding: 16px; text-align: center;">
                    <div style="color: #8b5cf6; font-size: 1.2rem; font-weight: 600;">{result.get('expectancy', 0)}%</div>
                    <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">Expectancy</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Long/Short breakdown
            if result.get('long_trades', 0) > 0 or result.get('short_trades', 0) > 0:
                long_trades = result.get('long_trades', 0)
                short_trades = result.get('short_trades', 0)
                long_wr = result.get('long_win_rate', 0)
                short_wr = result.get('short_win_rate', 0)
                
                st.markdown(f"""
                <div style="display: flex; gap: 16px; margin-bottom: 24px;">
                    <div style="flex: 1; background: rgba(0, 210, 106, 0.1); border: 1px solid rgba(0, 210, 106, 0.2); border-radius: 8px; padding: 12px 16px;">
                        <span style="color: #00d26a; font-weight: 600;">LONG:</span>
                        <span style="color: #94a3b8;"> {long_trades} trades ({long_wr}% WR)</span>
                    </div>
                    <div style="flex: 1; background: rgba(255, 71, 87, 0.1); border: 1px solid rgba(255, 71, 87, 0.2); border-radius: 8px; padding: 12px 16px;">
                        <span style="color: #ff4757; font-weight: 600;">SHORT:</span>
                        <span style="color: #94a3b8;"> {short_trades} trades ({short_wr}% WR)</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # Equity Curve
            if result.get('equity_curve'):
                st.markdown('<p style="color: #f8fafc; font-weight: 600; margin-bottom: 12px;">📈 Equity Curve</p>', unsafe_allow_html=True)
                eq_df = pd.DataFrame({
                    "Trade #": range(len(result['equity_curve'])),
                    "Equity": result['equity_curve']
                })
                st.line_chart(eq_df.set_index("Trade #"), width="stretch", height=300)

            # Trade History
            if result.get('trades'):
                st.markdown(f'<p style="color: #f8fafc; font-weight: 600; margin: 20px 0 12px 0;">📋 Trade History ({len(result["trades"])} trades)</p>', unsafe_allow_html=True)
                trades_df = pd.DataFrame(result['trades'])
                # Format columns
                display_cols = ['entry_time', 'exit_time', 'entry_price', 'exit_price', 'pnl_pct', 'exit_reason', 'bars_held']
                display_cols = [c for c in display_cols if c in trades_df.columns]
                st.dataframe(trades_df[display_cols], width="stretch", height=300)

                # Summary stats
                st.markdown(f"""
                <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 8px; padding: 12px 16px; margin-top: 12px;">
                    <span style="color: #64748b; font-size: 0.85rem;">
                        📅 Period: {result.get('start_date', 'N/A')} to {result.get('end_date', 'N/A')} | 
                        📊 Sharpe Ratio: {result.get('sharpe_ratio', 0)} | 
                        ⏱️ Avg Bars Held: {result.get('avg_bars_held', 0)}
                    </span>
                </div>
                """, unsafe_allow_html=True)

    # Optimization Section
    st.divider()
    with st.expander("Parameter Optimization (Advanced)"):
        st.warning("Optimization can take several minutes depending on the number of combinations.")

        opt_enabled = st.checkbox("Enable Optimization", key="opt_enabled")

        if opt_enabled:
            st.caption("Select parameter ranges to test:")
            opt_rsi = st.multiselect("RSI Max values", [52, 55, 58, 62, 65], default=[55, 58, 62], key="opt_rsi")
            opt_adx = st.multiselect("ADX Min values", [22, 25, 28, 32], default=[25, 28], key="opt_adx")
            opt_rr = st.multiselect("R:R values", [1.5, 1.8, 2.0, 2.5], default=[1.5, 1.8, 2.0], key="opt_rr")

            if st.button("Run Optimization", key="run_opt"):
                with st.spinner("Running optimization..."):
                    backtester = Backtester()
                    param_ranges = {
                        "rsi_buy": opt_rsi or [58],
                        "adx_min": opt_adx or [28],
                        "risk_reward": opt_rr or [1.8]
                    }

                    opt_results = backtester.optimize(
                        bt_ticker,
                        period=bt_period,
                        interval=bt_interval,
                        param_ranges=param_ranges
                    )

                    st.session_state['opt_results'] = opt_results

        if 'opt_results' in st.session_state and st.session_state['opt_results']:
            st.subheader("Optimization Results (Top 10)")
            opt_df = pd.DataFrame(st.session_state['opt_results'][:10])

            # Flatten params dict for display
            if 'params' in opt_df.columns:
                params_expanded = pd.json_normalize(opt_df['params'])
                opt_df = pd.concat([params_expanded, opt_df.drop('params', axis=1)], axis=1)

            display_cols = ['rsi_buy', 'adx_min', 'risk_reward', 'win_rate', 'profit_factor', 'total_return_pct', 'total_trades']
            display_cols = [c for c in display_cols if c in opt_df.columns]
            st.dataframe(opt_df[display_cols], width="stretch")

            best = st.session_state['opt_results'][0]
            st.success(f"Best params: RSI {best['params'].get('rsi_buy')}, ADX {best['params'].get('adx_min')}, "
                      f"R:R {best['params'].get('risk_reward')} -> PF {best['profit_factor']}, WR {best['win_rate']}%")

# TAB 6: STRATEGY INTELLIGENCE
with tabs[5]:
    st.markdown("""
    <div style="margin-bottom: 20px;">
        <h3 style="color: #f8fafc; margin: 0;">🎯 Strategy Intelligence</h3>
        <p style="color: #64748b; font-size: 0.9rem; margin-top: 4px;">Overview of what the bot has learned and how it makes decisions</p>
    </div>
    """, unsafe_allow_html=True)

    # Strategy Type Section
    strategy_type = getattr(current_bot, 'strategy_type', 'mean_reversion')

    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%); border-radius: 16px; padding: 24px; margin-bottom: 24px;">
        <div style="display: flex; align-items: center; gap: 16px;">
            <div style="background: rgba(255,255,255,0.2); padding: 16px; border-radius: 12px; font-size: 2rem;">
                {'📊' if strategy_type == 'mean_reversion' else '📈'}
            </div>
            <div>
                <h4 style="color: white; margin: 0; font-size: 1.4rem;">
                    {'Mean Reversion Strategy' if strategy_type == 'mean_reversion' else 'Momentum Strategy'}
                </h4>
                <p style="color: rgba(255,255,255,0.8); margin: 4px 0 0 0; font-size: 0.9rem;">
                    {'Bollinger Bands + RSI | 5m scalping | TP at middle BB' if strategy_type == 'mean_reversion' else 'ADX + EMA + RSI | 5m timeframe | ATR-based TP/SL'}
                </p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Strategy Parameters
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 12px; padding: 20px; height: 100%;">
            <h5 style="color: #3b82f6; margin: 0 0 16px 0;">📐 Strategy Parameters</h5>
        """, unsafe_allow_html=True)

        if strategy_type == 'mean_reversion':
            mean_rev = getattr(current_bot, 'mean_reversion', None)
            if mean_rev:
                st.markdown(f"""
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                    <div style="background: #252d3a; padding: 12px; border-radius: 8px;">
                        <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">BB Window</div>
                        <div style="color: #f8fafc; font-size: 1.1rem; font-weight: 600;">{mean_rev.bb_window}</div>
                    </div>
                    <div style="background: #252d3a; padding: 12px; border-radius: 8px;">
                        <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">BB Std Dev</div>
                        <div style="color: #f8fafc; font-size: 1.1rem; font-weight: 600;">{mean_rev.bb_std}</div>
                    </div>
                    <div style="background: #252d3a; padding: 12px; border-radius: 8px;">
                        <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">RSI Oversold</div>
                        <div style="color: #00d26a; font-size: 1.1rem; font-weight: 600;">&lt; {mean_rev.rsi_oversold}</div>
                    </div>
                    <div style="background: #252d3a; padding: 12px; border-radius: 8px;">
                        <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">RSI Overbought</div>
                        <div style="color: #ff4757; font-size: 1.1rem; font-weight: 600;">&gt; {mean_rev.rsi_overbought}</div>
                    </div>
                    <div style="background: #252d3a; padding: 12px; border-radius: 8px; grid-column: span 2;">
                        <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">ATR SL Multiplier</div>
                        <div style="color: #f8fafc; font-size: 1.1rem; font-weight: 600;">{mean_rev.atr_sl_mult}x</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            cfg = getattr(current_bot, 'strategy_config', {})
            st.markdown(f"""
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div style="background: #252d3a; padding: 12px; border-radius: 8px;">
                    <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">RSI Buy</div>
                    <div style="color: #f8fafc; font-size: 1.1rem; font-weight: 600;">{cfg.get('rsi_buy', 58)}</div>
                </div>
                <div style="background: #252d3a; padding: 12px; border-radius: 8px;">
                    <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">ADX Min</div>
                    <div style="color: #f8fafc; font-size: 1.1rem; font-weight: 600;">{cfg.get('adx_min', 28)}</div>
                </div>
                <div style="background: #252d3a; padding: 12px; border-radius: 8px;">
                    <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">Risk:Reward</div>
                    <div style="color: #8b5cf6; font-size: 1.1rem; font-weight: 600;">{cfg.get('risk_reward', 1.8)}</div>
                </div>
                <div style="background: #252d3a; padding: 12px; border-radius: 8px;">
                    <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">ATR SL Mult</div>
                    <div style="color: #f8fafc; font-size: 1.1rem; font-weight: 600;">{cfg.get('atr_sl_mult', 1.5)}x</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 12px; padding: 20px; height: 100%;">
            <h5 style="color: #00d26a; margin: 0 0 16px 0;">📡 Data Sources</h5>
            <div style="display: flex; flex-direction: column; gap: 12px;">
                <div style="background: #252d3a; padding: 12px; border-radius: 8px; display: flex; align-items: center; gap: 12px;">
                    <div style="background: #3b82f6; padding: 8px; border-radius: 6px;">📊</div>
                    <div>
                        <div style="color: #f8fafc; font-weight: 500;">Yahoo Finance (yfinance)</div>
                        <div style="color: #64748b; font-size: 0.8rem;">Historical OHLCV data</div>
                    </div>
                </div>
                <div style="background: #252d3a; padding: 12px; border-radius: 8px; display: flex; align-items: center; gap: 12px;">
                    <div style="background: #8b5cf6; padding: 8px; border-radius: 6px;">⏱️</div>
                    <div>
                        <div style="color: #f8fafc; font-weight: 500;">5m Scalping</div>
                        <div style="color: #64748b; font-size: 0.8rem;">Mean Reversion timeframe</div>
                    </div>
                </div>
                <div style="background: #252d3a; padding: 12px; border-radius: 8px; display: flex; align-items: center; gap: 12px;">
                    <div style="background: #00d26a; padding: 8px; border-radius: 6px;">🔄</div>
                    <div>
                        <div style="color: #f8fafc; font-weight: 500;">Real-time via Capital.com</div>
                        <div style="color: #64748b; font-size: 0.8rem;">Live execution & prices</div>
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div style="height: 24px;"></div>', unsafe_allow_html=True)

    # Trading Assets Section
    st.markdown("""
    <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 12px; padding: 20px; margin-bottom: 24px;">
        <h5 style="color: #fbbf24; margin: 0 0 16px 0;">📈 Trading Universe (30 Assets)</h5>
    """, unsafe_allow_html=True)

    # Get priority tickers from bot
    priority_tickers = getattr(current_bot, 'priority_tickers', [])

    if priority_tickers:
        # Group by category
        categories = {}
        for ticker in priority_tickers:
            cat = ticker.get('cat', 'Other')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(ticker)

        # Display each category
        cat_cols = st.columns(len(categories))
        cat_colors = {
            'Crypto': '#fbbf24',
            'Forex': '#3b82f6',
            'US Stocks': '#00d26a'
        }

        for idx, (cat_name, tickers) in enumerate(categories.items()):
            with cat_cols[idx]:
                color = cat_colors.get(cat_name, '#8b5cf6')
                st.markdown(f"""
                <div style="background: #252d3a; border-radius: 10px; padding: 16px;">
                    <h6 style="color: {color}; margin: 0 0 12px 0; display: flex; align-items: center; gap: 8px;">
                        {'🪙' if cat_name == 'Crypto' else '💱' if cat_name == 'Forex' else '📊'} {cat_name}
                        <span style="background: {color}20; color: {color}; padding: 2px 8px; border-radius: 10px; font-size: 0.7rem;">{len(tickers)}</span>
                    </h6>
                """, unsafe_allow_html=True)

                for t in tickers:
                    pf = t.get('pf', 0)
                    wr = t.get('wr', 0)
                    pf_color = '#00d26a' if pf > 1.5 else '#fbbf24' if pf > 1 else '#ff4757'
                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #2d3748;">
                        <div>
                            <span style="color: #f8fafc; font-weight: 500;">{t.get('name', t.get('epic', 'N/A'))}</span>
                            <span style="color: #64748b; font-size: 0.75rem; margin-left: 4px;">{t.get('epic', '')}</span>
                        </div>
                        <div style="display: flex; gap: 8px;">
                            <span style="background: {pf_color}20; color: {pf_color}; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem;">PF {pf:.1f}</span>
                            <span style="background: #3b82f620; color: #3b82f6; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem;">{wr}% WR</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No priority tickers configured")

    st.markdown("</div>", unsafe_allow_html=True)

    # Strategy Logic Explanation
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        <div style="background: linear-gradient(145deg, #1e2530 0%, #252d3a 100%); border: 1px solid #00d26a40; border-radius: 12px; padding: 20px;">
            <h5 style="color: #00d26a; margin: 0 0 16px 0;">🟢 BUY Signal Conditions</h5>
            <div style="color: #94a3b8; font-size: 0.9rem; line-height: 1.8;">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <span style="color: #00d26a;">✓</span> Price touches lower Bollinger Band
                </div>
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <span style="color: #00d26a;">✓</span> RSI below 40 (oversold)
                </div>
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <span style="color: #00d26a;">✓</span> Take Profit: Middle BB (mean)
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="color: #00d26a;">✓</span> Stop Loss: 2x ATR below entry
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div style="background: linear-gradient(145deg, #1e2530 0%, #252d3a 100%); border: 1px solid #ff475740; border-radius: 12px; padding: 20px;">
            <h5 style="color: #ff4757; margin: 0 0 16px 0;">🔴 SELL Signal Conditions</h5>
            <div style="color: #94a3b8; font-size: 0.9rem; line-height: 1.8;">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <span style="color: #ff4757;">✓</span> Price touches upper Bollinger Band
                </div>
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <span style="color: #ff4757;">✓</span> RSI above 60 (overbought)
                </div>
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <span style="color: #ff4757;">✓</span> Take Profit: Middle BB (mean)
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="color: #ff4757;">✓</span> Stop Loss: 2x ATR above entry
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div style="height: 24px;"></div>', unsafe_allow_html=True)

    # Backtest Summary
    st.markdown("""
    <div style="background: linear-gradient(145deg, #1e2530 0%, #252d3a 100%); border: 1px solid #8b5cf640; border-radius: 12px; padding: 20px;">
        <h5 style="color: #8b5cf6; margin: 0 0 16px 0;">📊 Strategy Performance (Backtest)</h5>
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;">
            <div style="text-align: center;">
                <div style="color: #00d26a; font-size: 1.8rem; font-weight: 700;">56.1%</div>
                <div style="color: #64748b; font-size: 0.75rem; text-transform: uppercase;">Win Rate</div>
            </div>
            <div style="text-align: center;">
                <div style="color: #3b82f6; font-size: 1.8rem; font-weight: 700;">33.5%</div>
                <div style="color: #64748b; font-size: 0.75rem; text-transform: uppercase;">Return (2mo)</div>
            </div>
            <div style="text-align: center;">
                <div style="color: #fbbf24; font-size: 1.8rem; font-weight: 700;">~10</div>
                <div style="color: #64748b; font-size: 0.75rem; text-transform: uppercase;">Trades/Day</div>
            </div>
            <div style="text-align: center;">
                <div style="color: #8b5cf6; font-size: 1.8rem; font-weight: 700;">4.3x</div>
                <div style="color: #64748b; font-size: 0.75rem; text-transform: uppercase;">Return (1:10)</div>
            </div>
        </div>
        <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid #2d3748;">
            <div style="color: #64748b; font-size: 0.85rem;">
                💡 <strong>With 2000 Kč initial + 1:10 leverage:</strong>
                <span style="color: #00d26a; font-weight: 600;">2000 Kč → 8693 Kč</span> (2 months)
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# TAB 7: LEARNING DASHBOARD
with tabs[6]:
    st.markdown("""
    <div style="margin-bottom: 20px;">
        <h3 style="color: #f8fafc; margin: 0;">🤖 Self-Learning Dashboard</h3>
        <p style="color: #64748b; font-size: 0.9rem; margin-top: 4px;">Kompletní přehled všeho co bot dělá a proč</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Get learning engine from bot
    learning_engine = getattr(current_bot, 'learning_engine', None)
    
    if learning_engine:
        summary = learning_engine.get_stats_summary()
        ticker_stats = dict(learning_engine.ticker_stats)
        learned_params = learning_engine.learned_params
        
        # =====================================================
        # HLAVNÍ METRIKY
        # =====================================================
        st.markdown("""
        <div style="background: linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%); border-radius: 16px; padding: 24px; margin-bottom: 24px;">
            <div style="display: flex; align-items: center; gap: 16px;">
                <div style="background: rgba(255,255,255,0.2); padding: 16px; border-radius: 12px; font-size: 2rem;">🧠</div>
                <div>
                    <h4 style="color: white; margin: 0; font-size: 1.4rem;">Self-Learning Engine Active</h4>
                    <p style="color: rgba(255,255,255,0.8); margin: 4px 0 0 0; font-size: 0.9rem;">
                        Bot analyzuje každý obchod a automaticky upravuje strategii
                    </p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # KPI Cards
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_trades = summary.get('total_trades', 0)
            st.markdown(f"""
            <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 12px; padding: 20px; text-align: center;">
                <div style="color: #3b82f6; font-size: 2rem; font-weight: 700;">{total_trades}</div>
                <div style="color: #64748b; font-size: 0.75rem; text-transform: uppercase;">Zaznamenaných obchodů</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            wr = summary.get('overall_win_rate', 0)
            wr_color = "#00d26a" if wr >= 50 else "#fbbf24" if wr >= 40 else "#ff4757"
            st.markdown(f"""
            <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 12px; padding: 20px; text-align: center;">
                <div style="color: {wr_color}; font-size: 2rem; font-weight: 700;">{wr:.1f}%</div>
                <div style="color: #64748b; font-size: 0.75rem; text-transform: uppercase;">Celková úspěšnost</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            total_pnl = summary.get('total_pnl', 0)
            pnl_color = "#00d26a" if total_pnl >= 0 else "#ff4757"
            st.markdown(f"""
            <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 12px; padding: 20px; text-align: center;">
                <div style="color: {pnl_color}; font-size: 2rem; font-weight: 700;">${total_pnl:+.2f}</div>
                <div style="color: #64748b; font-size: 0.75rem; text-transform: uppercase;">Celkový P&L</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            blacklisted = summary.get('auto_blacklisted_count', 0)
            st.markdown(f"""
            <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 12px; padding: 20px; text-align: center;">
                <div style="color: #ff4757; font-size: 2rem; font-weight: 700;">{blacklisted}</div>
                <div style="color: #64748b; font-size: 0.75rem; text-transform: uppercase;">Auto-blacklisted</div>
            </div>
            """, unsafe_allow_html=True)
        
        # LONG vs SHORT performance
        long_stats = summary.get("long_stats", {})
        short_stats = summary.get("short_stats", {})
        long_wr = long_stats.get("win_rate", 0)
        short_wr = short_stats.get("win_rate", 0)
        long_trades = long_stats.get("trades", 0)
        short_trades = short_stats.get("trades", 0)
        shorts_enabled = learned_params.get("enable_shorts", True)

        st.markdown('<div style="height: 16px;"></div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown(f"""
            <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 12px; padding: 16px; text-align: center;">
                <div style="color: #00d26a; font-size: 1.4rem; font-weight: 700;">{long_wr:.0f}%</div>
                <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">LONG Win Rate</div>
                <div style="color: #94a3b8; font-size: 0.7rem;">{long_trades} trades</div>
            </div>
            """, unsafe_allow_html=True)

        with c2:
            st.markdown(f"""
            <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 12px; padding: 16px; text-align: center;">
                <div style="color: #ff4757; font-size: 1.4rem; font-weight: 700;">{short_wr:.0f}%</div>
                <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">SHORT Win Rate</div>
                <div style="color: #94a3b8; font-size: 0.7rem;">{short_trades} trades</div>
            </div>
            """, unsafe_allow_html=True)

        with c3:
            status_color = "#00d26a" if shorts_enabled else "#ff4757"
            status_text = "ENABLED" if shorts_enabled else "DISABLED"
            st.markdown(f"""
            <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 12px; padding: 16px; text-align: center;">
                <div style="color: {status_color}; font-size: 1.4rem; font-weight: 700;">{status_text}</div>
                <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">Auto SHORT Toggle</div>
                <div style="color: #94a3b8; font-size: 0.7rem;">Learning engine</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<div style="height: 24px;"></div>', unsafe_allow_html=True)
        
        # =====================================================
        # KOMPLETNÍ PŘEHLED - co se stalo
        # =====================================================
        overview_tabs = st.tabs(["📋 Activity Log", "📊 Aktuální Watchlist", "🚫 Blacklist"])
        
        with overview_tabs[0]:
            activity_log = getattr(learning_engine, 'activity_log', [])
            if activity_log:
                st.markdown("**Chronologický log událostí (nejnovější nahoře)**")
                for e in reversed(activity_log[-80:]):
                    t = e.get('type', '')
                    msg = e.get('message', '')
                    tm = e.get('time', '')
                    if t == 'trade':
                        color = "#00d26a" if "PnL $+" in msg else "#ff4757"
                    elif t == 'blacklist':
                        color = "#ff4757"
                    elif t == 'params':
                        color = "#3b82f6"
                    else:
                        color = "#94a3b8"
                    st.markdown(f"<div style='padding: 8px; border-left: 4px solid {color}; margin-bottom: 8px; background: #1e2530; border-radius: 6px;'><span style='color: #64748b; font-size: 0.8rem;'>{tm}</span> <span style='color: {color};'>{msg}</span></div>", unsafe_allow_html=True)
            else:
                st.info("Zatím žádné události. Bot musí udělat obchody.")
        
        with overview_tabs[1]:
            watchlist = []
            if hasattr(current_bot, '_get_dynamic_watchlist'):
                try:
                    watchlist = current_bot._get_dynamic_watchlist(50)
                except Exception:
                    watchlist = getattr(current_bot, 'open_instruments', []) or getattr(current_bot, 'priority_tickers', [])[:20]
            else:
                watchlist = getattr(current_bot, 'open_instruments', []) or getattr(current_bot, 'priority_tickers', [])[:20]
            
            if watchlist:
                st.markdown(f"**Bot právě skenuje {len(watchlist)} assetů**")
                names = [str(w.get('epic') or w.get('yf') or w.get('t212') or w) for w in watchlist]
                st.markdown(", ".join(names) if isinstance(names[0], str) else str(names))
                df_wl = pd.DataFrame([{"Epic": w.get('epic',''), "YF": w.get('yf',''), "Název": w.get('name','')} for w in watchlist[:30]])
                st.dataframe(df_wl, width="stretch", hide_index=True)
            else:
                st.info("Watchlist bude k dispozici po startu bota.")
        
        with overview_tabs[2]:
            bl_manual = getattr(current_bot, 'ticker_blacklist', [])
            bl_auto = learning_engine.get_blacklisted_tickers()
            bl_auto_reasons = {t: learning_engine.ticker_stats.get(t, {}).get('blacklist_reason', '') for t in bl_auto}
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Manuální blacklist**")
                st.markdown(", ".join(bl_manual[:30]) if bl_manual else "—")
            with col2:
                st.markdown("**Auto-blacklist (důvod)**")
                for t, r in list(bl_auto_reasons.items())[:15]:
                    st.markdown(f"- **{t}**: {r}")
                if not bl_auto:
                    st.markdown("—")
        
        st.markdown('<div style="height: 24px;"></div>', unsafe_allow_html=True)
        
        # =====================================================
        # NAUČENÉ PARAMETRY
        # =====================================================
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 12px; padding: 20px;">
                <h5 style="color: #8b5cf6; margin: 0 0 16px 0;">⚙️ Naučené parametry</h5>
            """, unsafe_allow_html=True)
            
            params_html = ""
            param_labels = {
                "rsi_oversold": ("RSI Oversold", "Práh pro BUY signál"),
                "rsi_overbought": ("RSI Overbought", "Práh pro SELL signál"),
                "atr_sl_mult": ("ATR SL Multiplier", "Šířka stop-lossu"),
                "min_confidence": ("Min Confidence", "Minimální jistota signálu"),
                "enable_shorts": ("SHORT pozice", "Povolit prodej nakrátko"),
            }
            
            for key, value in learned_params.items():
                label, desc = param_labels.get(key, (key, ""))
                if isinstance(value, bool):
                    val_display = "✅ Zapnuto" if value else "❌ Vypnuto"
                    val_color = "#00d26a" if value else "#ff4757"
                elif isinstance(value, float):
                    val_display = f"{value:.2f}"
                    val_color = "#f8fafc"
                else:
                    val_display = str(value)
                    val_color = "#f8fafc"
                
                params_html += f"""
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #2d3748;">
                    <div>
                        <div style="color: #f8fafc; font-weight: 500;">{label}</div>
                        <div style="color: #64748b; font-size: 0.75rem;">{desc}</div>
                    </div>
                    <div style="color: {val_color}; font-weight: 600;">{val_display}</div>
                </div>
                """
            
            st.markdown(params_html + "</div>", unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 12px; padding: 20px;">
                <h5 style="color: #00d26a; margin: 0 0 16px 0;">📈 Projekce zisku</h5>
            """, unsafe_allow_html=True)
            
            # Calculate projections
            if total_trades > 0 and total_pnl != 0:
                avg_pnl_per_trade = total_pnl / total_trades
                
                # Estimate trades per day (based on recent activity)
                trades_per_day = max(1, total_trades / 7)  # Assume 7 days of data
                
                daily_projection = avg_pnl_per_trade * trades_per_day
                weekly_projection = daily_projection * 5  # 5 trading days
                monthly_projection = daily_projection * 22  # 22 trading days
                
                proj_color = "#00d26a" if monthly_projection > 0 else "#ff4757"
                
                st.markdown(f"""
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                    <div style="background: #252d3a; padding: 12px; border-radius: 8px; text-align: center;">
                        <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">Průměr/obchod</div>
                        <div style="color: {'#00d26a' if avg_pnl_per_trade > 0 else '#ff4757'}; font-size: 1.2rem; font-weight: 600;">${avg_pnl_per_trade:+.2f}</div>
                    </div>
                    <div style="background: #252d3a; padding: 12px; border-radius: 8px; text-align: center;">
                        <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">Obchodů/den</div>
                        <div style="color: #3b82f6; font-size: 1.2rem; font-weight: 600;">~{trades_per_day:.1f}</div>
                    </div>
                    <div style="background: #252d3a; padding: 12px; border-radius: 8px; text-align: center;">
                        <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">Týdenní projekce</div>
                        <div style="color: {proj_color}; font-size: 1.2rem; font-weight: 600;">${weekly_projection:+.2f}</div>
                    </div>
                    <div style="background: #252d3a; padding: 12px; border-radius: 8px; text-align: center;">
                        <div style="color: #64748b; font-size: 0.7rem; text-transform: uppercase;">Měsíční projekce</div>
                        <div style="color: {proj_color}; font-size: 1.5rem; font-weight: 700;">${monthly_projection:+.2f}</div>
                    </div>
                </div>
                
                <div style="margin-top: 16px; padding: 12px; background: {'rgba(0, 210, 106, 0.1)' if monthly_projection > 0 else 'rgba(255, 71, 87, 0.1)'}; border-radius: 8px;">
                    <div style="color: {'#00d26a' if monthly_projection > 0 else '#ff4757'}; font-size: 0.85rem;">
                        {'📈' if monthly_projection > 0 else '📉'} S pákou 1:10: <strong>${monthly_projection * 10:+.2f}/měsíc</strong>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="text-align: center; padding: 40px; color: #64748b;">
                    <div style="font-size: 2rem; margin-bottom: 8px;">📊</div>
                    <div>Zatím nedostatek dat pro projekci</div>
                    <div style="font-size: 0.8rem; margin-top: 4px;">Bot potřebuje více obchodů</div>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown('<div style="height: 24px;"></div>', unsafe_allow_html=True)
        
        # =====================================================
        # VÝKON PODLE TICKERŮ
        # =====================================================
        st.markdown("""
        <div style="background: #1e2530; border: 1px solid #2d3748; border-radius: 12px; padding: 20px; margin-bottom: 24px;">
            <h5 style="color: #fbbf24; margin: 0 0 16px 0;">📊 Výkon podle tickerů</h5>
        """, unsafe_allow_html=True)
        
        if ticker_stats:
            # Sort by profit factor
            sorted_tickers = sorted(
                ticker_stats.items(),
                key=lambda x: x[1].get('profit_factor', 0),
                reverse=True
            )
            
            ticker_rows = ""
            for ticker, stats in sorted_tickers:
                if stats.get('trades', 0) == 0:
                    continue
                    
                trades = stats.get('trades', 0)
                wins = stats.get('wins', 0)
                wr = stats.get('win_rate', 0)
                pf = stats.get('profit_factor', 0)
                pnl = stats.get('total_pnl', 0)
                is_blacklisted = stats.get('auto_blacklisted', False)
                blacklist_reason = stats.get('blacklist_reason', '')
                
                # Color coding
                if is_blacklisted:
                    row_bg = "rgba(255, 71, 87, 0.1)"
                    status_badge = f'<span style="background: #ff4757; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem;">BLACKLISTED</span>'
                elif pf >= 1.5:
                    row_bg = "rgba(0, 210, 106, 0.1)"
                    status_badge = f'<span style="background: #00d26a; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem;">EXCELLENT</span>'
                elif pf >= 1.0:
                    row_bg = "rgba(251, 191, 36, 0.1)"
                    status_badge = f'<span style="background: #fbbf24; color: black; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem;">PROFITABLE</span>'
                else:
                    row_bg = "rgba(148, 163, 184, 0.05)"
                    status_badge = f'<span style="background: #64748b; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem;">LOSING</span>'
                
                wr_color = "#00d26a" if wr >= 50 else "#fbbf24" if wr >= 40 else "#ff4757"
                pf_color = "#00d26a" if pf >= 1.5 else "#fbbf24" if pf >= 1.0 else "#ff4757"
                pnl_color = "#00d26a" if pnl >= 0 else "#ff4757"
                
                ticker_rows += f"""
                <div style="display: grid; grid-template-columns: 1fr 80px 80px 80px 100px 120px; gap: 8px; align-items: center; padding: 12px; background: {row_bg}; border-radius: 8px; margin-bottom: 8px;">
                    <div>
                        <div style="color: #f8fafc; font-weight: 600;">{ticker}</div>
                        <div style="color: #64748b; font-size: 0.7rem;">{blacklist_reason if is_blacklisted else f'{trades} obchodů'}</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="color: {wr_color}; font-weight: 600;">{wr:.0f}%</div>
                        <div style="color: #64748b; font-size: 0.65rem;">Win Rate</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="color: {pf_color}; font-weight: 600;">{pf:.2f}</div>
                        <div style="color: #64748b; font-size: 0.65rem;">PF</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="color: #f8fafc;">{wins}/{trades}</div>
                        <div style="color: #64748b; font-size: 0.65rem;">W/L</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="color: {pnl_color}; font-weight: 600;">${pnl:+.2f}</div>
                        <div style="color: #64748b; font-size: 0.65rem;">P&L</div>
                    </div>
                    <div style="text-align: right;">{status_badge}</div>
                </div>
                """
            
            if ticker_rows:
                st.markdown(ticker_rows, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="text-align: center; padding: 20px; color: #64748b;">
                    Zatím žádné zaznamenané obchody
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="text-align: center; padding: 20px; color: #64748b;">
                Zatím žádné zaznamenané obchody
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        # =====================================================
        # CO BOT ZMĚNÍ / PROČ
        # =====================================================
        st.markdown("""
        <div style="background: linear-gradient(145deg, #1e2530 0%, #252d3a 100%); border: 1px solid #3b82f640; border-radius: 12px; padding: 20px; margin-bottom: 24px;">
            <h5 style="color: #3b82f6; margin: 0 0 16px 0;">🔄 Plánované změny (Auto-optimalizace)</h5>
        """, unsafe_allow_html=True)
        
        changes = []
        
        # Analyze what bot will change
        overall_wr = summary.get('overall_win_rate', 50)
        
        if overall_wr < 40:
            changes.append({
                "change": "Zvýšit selektivitu vstupů",
                "reason": f"Win rate je pouze {overall_wr:.0f}% (cíl: 50%+)",
                "action": "Snížit RSI oversold práh → méně, ale kvalitnější signály",
                "icon": "🎯"
            })
        
        if overall_wr > 60 and total_trades > 10:
            changes.append({
                "change": "Mírně uvolnit filtry",
                "reason": f"Win rate {overall_wr:.0f}% je výborný - můžeme mít více obchodů",
                "action": "Zvýšit RSI oversold práh → více příležitostí",
                "icon": "📈"
            })
        
        blacklisted_tickers = learning_engine.get_blacklisted_tickers()
        if blacklisted_tickers:
            changes.append({
                "change": f"Blokovat {len(blacklisted_tickers)} tickerů",
                "reason": "Opakované ztráty nebo nízká úspěšnost",
                "action": f"Auto-blacklist: {', '.join(blacklisted_tickers[:5])}{'...' if len(blacklisted_tickers) > 5 else ''}",
                "icon": "🚫"
            })
        
        # Check shorts performance (simplified)
        if not learned_params.get('enable_shorts', True):
            changes.append({
                "change": "SHORT pozice vypnuty",
                "reason": "Analýza ukázala nízkou úspěšnost SHORT obchodů",
                "action": "Bot obchoduje pouze LONG pozice",
                "icon": "📊"
            })
        
        if not changes:
            changes.append({
                "change": "Žádné změny neplánované",
                "reason": "Současné parametry fungují dobře",
                "action": "Bot bude pokračovat se stávající konfigurací",
                "icon": "✅"
            })
        
        for change in changes:
            st.markdown(f"""
            <div style="background: #252d3a; border-radius: 10px; padding: 16px; margin-bottom: 12px;">
                <div style="display: flex; gap: 12px;">
                    <div style="font-size: 1.5rem;">{change['icon']}</div>
                    <div style="flex: 1;">
                        <div style="color: #f8fafc; font-weight: 600; margin-bottom: 4px;">{change['change']}</div>
                        <div style="color: #94a3b8; font-size: 0.85rem; margin-bottom: 8px;">{change['reason']}</div>
                        <div style="color: #3b82f6; font-size: 0.8rem; background: rgba(59, 130, 246, 0.1); padding: 8px; border-radius: 6px;">
                            → {change['action']}
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        # =====================================================
        # PRAVIDLA UČENÍ
        # =====================================================
        with st.expander("📖 Jak se bot učí", expanded=False):
            st.markdown("""
            ### Auto-Blacklist pravidla
            
            Ticker je automaticky zablokován pokud:
            - **4+ ztrát v řadě** na stejném tickeru
            - **Win rate < 35%** po minimálně 5 obchodech
            - **Profit factor < 0.7** (ztráty převyšují zisky)
            
            ### Optimalizace parametrů
            
            Bot automaticky upravuje:
            - **RSI prahy** - podle celkové úspěšnosti
            - **SHORT/LONG** - vypne SHORT pokud nefunguje
            - **Confidence threshold** - zvýší pokud je moc ztrát
            
            ### Kdy se bot učí
            
            - Po každém uzavřeném obchodu
            - Při startu bota (analýza historie)
            - Data se ukládají do Supabase (cloud) nebo lokálně
            
            ### Reset učení
            
            Pokud chcete resetovat naučená data:
            ```python
            learning_engine.reset_ticker("GBPUSD")  # Reset jednoho tickeru
            ```
            """)
        
    else:
        st.warning("Learning Engine není aktivní. Spusťte bota pro aktivaci učení.")
        st.markdown("""
        ### Jak aktivovat Learning Engine:
        
        1. Spusťte bota pomocí tlačítka **START**
        2. Bot automaticky začne zaznamenávat obchody
        3. Po několika obchodech uvidíte statistiky zde
        
        ### Co Learning Engine dělá:
        
        - 📊 Sleduje výkon každého tickeru
        - 🚫 Automaticky blokuje ztrátové tickery
        - ⚙️ Optimalizuje parametry strategie
        - 📈 Počítá projekce zisku
        """)

# Footer / Auto-Refresh handled by fragments


# TAB 7: LEARNING
with tabs[6]:
    st.markdown("""
    <div style="margin-bottom: 20px;">
        <h3 style="color: #f8fafc; margin: 0;">🤖 Learning Engine Stats</h3>
        <p style="color: #64748b; font-size: 0.9rem; margin-top: 4px;">Real-time insights into the bot's self-improvement process</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Get real data from Learning Engine
    le = current_bot.learning_engine
    
    # 1. Top Assets (from ticker_stats)
    ticker_stats = le.ticker_stats
    
    l_col1, l_col2 = st.columns(2)
    
    with l_col1:
        st.markdown("**🏆 Top Performing Assets**")
        if ticker_stats:
            # Convert to DF
            data = []
            for t, s in ticker_stats.items():
                if s['trades'] > 0:
                    data.append({
                        "Asset": t,
                        "Generates": f"${s['total_pnl']:.2f}",
                        "WinRate": f"{s['win_rate']:.0f}%",
                        "Trades": s['trades'],
                        "PF": s['profit_factor']
                    })
            
            if data:
                df_top = pd.DataFrame(data)
                # Sort by Profit (Generates)
                df_top['Profit_Val'] = df_top['Generates'].apply(lambda x: float(x.replace("$","")))
                df_top = df_top.sort_values('Profit_Val', ascending=False).head(10)
                df_top = df_top.drop('Profit_Val', axis=1)
                
                st.dataframe(df_top, width="stretch", hide_index=True)
            else:
                st.info("No trading data available yet.")
        else:
            st.info("No trading data available yet.")
            
    with l_col2:
        st.markdown("**🚫 Blacklisted (Avoided)**")
        blacklisted = le.get_blacklisted_tickers()
        if blacklisted:
            b_data = []
            for t in blacklisted:
                reason = ticker_stats[t].get('blacklist_reason', 'Unknown')
                b_data.append({"Asset": t, "Reason": reason})
            
            df_black = pd.DataFrame(b_data)
            st.dataframe(df_black, width="stretch", hide_index=True)
        else:
            st.success("✅ No assets blacklisted. Bot is trading everything.")

    st.markdown("### 📈 Learning Progress (Cumulative P&L)")
    
    # Extract P&L history from activity log
    # Log format: "trade", "{ticker} {direction} PnL ${pnl}"
    import re
    
    pnl_history = []
    cumulative_pnl = 0.0
    
    logs = le.activity_log
    for log in logs:
        if log['type'] == 'trade':
            msg = log['message']
            # Parse PnL
            match = re.search(r'PnL\s\$([+\-]?\d+\.?\d*)', msg)
            if match:
                try:
                    pnl = float(match.group(1))
                    cumulative_pnl += pnl
                    pnl_history.append({
                        "Time": log['time'],
                        "Total PnL": cumulative_pnl
                    })
                except:
                    pass
    
    if pnl_history:
        df_chart = pd.DataFrame(pnl_history)
        st.line_chart(df_chart.set_index("Time"), width="stretch", color="#00f2ea")
    else:
        st.info("Waiting for completed trades to build learning curve...")
    
    st.caption("Data is updated dynamically as the bot learns from closed trades.")


# TAB 8: ECONOMIC CALENDAR
with tabs[7]:
    st.markdown("""
    <div style="margin-bottom: 20px;">
        <h3 style="color: #f8fafc; margin: 0;">📅 Economic Calendar</h3>
        <p style="color: #64748b; font-size: 0.9rem; margin-top: 4px;">Major market-moving events and news</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Refresh button
    if st.button("🔄 Refresh Data", key="refresh_cal"):
        st.cache_data.clear()
        
    try:
        events_df = get_economic_calendar()
        
        if not events_df.empty:
            # Stats (High Impact count)
            high_impact_count = len(events_df[events_df['Impact'] == 'High'])
            
            if high_impact_count > 0:
                st.warning(f"⚠️ {high_impact_count} High Impact Events detected today! Volatility Expected.")
            else:
                st.success("✅ No major scheduled risk events detected today.")
            
            # Display Table
            st.markdown("### Today's Events")
            
            # Styling
            def color_impact(val):
                if val == 'High':
                    return 'color: #ff4757; font-weight: bold'
                elif val == 'Medium':
                    return 'color: #fbbf24; font-weight: bold'
                return 'color: #94a3b8'
            
            styled_events = events_df.style.map(color_impact, subset=['Impact'])
            st.dataframe(styled_events, width="stretch", hide_index=True)
            
        else:
            st.info("No major events found for today.")
            
    except Exception as e:
        st.error(f"Failed to load calendar data: {str(e)}")
        
    # Manual Event Entry (Optional - for user to add notes)
    with st.expander("📝 Add Custom Event Note"):
        st.text_input("Event Name", placeholder="e.g. Fed Speech")
        st.time_input("Time")
        if st.button("Add Note"):
            st.toast("Note added (simulation)")
