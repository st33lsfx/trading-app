from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import os
import sys
import pandas as pd
from dotenv import load_dotenv

# Ensure we can import local modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from capital_client import CapitalClient
from strategy import Strategy

load_dotenv()

app = FastAPI()

# CORS for Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, set to specific domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Client
API_KEY = os.getenv("CAPITAL_API_KEY")
LOGIN = os.getenv("CAPITAL_LOGIN")
PASS = os.getenv("CAPITAL_PASSWORD")
BASE_URL = os.getenv("CAPITAL_BASE_URL", "https://demo-api-capital.backend-capital.com")

import time

# Singleton Client Instance
CLIENT = None
LAST_AUTH_TRY = 0
AUTH_COOLDOWN = 60 # Seconds to wait after failure

def get_client():
    global CLIENT, LAST_AUTH_TRY
    
    if CLIENT is not None:
        return CLIENT
        
    # Check Cooldown
    if time.time() - LAST_AUTH_TRY < AUTH_COOLDOWN:
        raise HTTPException(status_code=503, detail="Rate Limit Cooldown. Please wait 1 min.")

    if not API_KEY or not LOGIN or not PASS:
        raise HTTPException(status_code=500, detail="Missing API Credentials")
    
    try:
        LAST_AUTH_TRY = time.time()
        print("Initializing Capital Client...")
        CLIENT = CapitalClient(API_KEY, LOGIN, PASS, BASE_URL)
        return CLIENT
    except Exception as e:
        print(f"Failed to init client: {e}")
        # If 429, we are definitely in penalty box
        raise HTTPException(status_code=500, detail=f"Auth Failed: {e}")

@app.get("/api/status")
def get_status():
    """Check API status and account balance."""
    try:
        client = get_client()
        account = client.get_account_info()
        return {"status": "online", "account": account}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/positions")
def get_positions():
    """Get open positions."""
    try:
        client = get_client()
        positions = client.get_positions()
        # Verify valid response
        if isinstance(positions, dict) and 'errorCode' in positions:
             # Token might be expired, force re-auth next time?
             # For now just return empty list or error
             print(f"Position fetch error: {positions}")
             return []
        return positions
    except Exception as e:
        print(f"Position Error: {e}")
        return []

# Global In-Memory State (For Demo/Local)
# In production Vercel, use KV or Database
LOG_BUFFER = []
SETTINGS = {
    "broker": "capital", # or 't212'
    "categories": ["Forex", "Crypto"],
    "risk": "medium"
}

def log(msg):
    """Helper to add log."""
    print(msg)
    LOG_BUFFER.insert(0, f"[{pd.Timestamp.now().strftime('%H:%M:%S')}] {msg}")
    if len(LOG_BUFFER) > 100: LOG_BUFFER.pop()

@app.get("/api/logs")
def get_logs():
    return LOG_BUFFER

@app.get("/api/settings")
def get_settings():
    return SETTINGS

@app.post("/api/settings")
async def update_settings(request: Request):
    data = await request.json()
    SETTINGS.update(data)
    log(f"Settings updated: {SETTINGS}")
    return {"status": "ok", "settings": SETTINGS}

@app.get("/api/cron")
def run_cron_job(request: Request):
    """
    CRON JOB: Runs every minute via Vercel Cron.
    Scans the market and executes trades.
    """
# Cache for market list to avoid fetching every minute
MARKET_CACHE = {}

@app.get("/api/cron")
def run_cron_job(request: Request):
    """
    CRON JOB: Runs every minute via Vercel Cron.
    Scans the market and executes trades.
    """
    try:
        client = get_client()
        log("🚀 Cron Job Started: Scanning Markets...")
        
        # 1. Get Active Settings
        active_cats = SETTINGS.get("categories", [])
        log(f"Active Categories: {active_cats}")
        
        # 2. Build/Update Watchlist (Dynamic)
        # We cache it in memory for the life of the instance (Vercel might recycle, which is fine)
        watchlist = []
        
        # Helper to populate cache if missing
        if not MARKET_CACHE:
            log("Fetching Market Navigation (First Run)...")
            # Map of Category Name -> Node ID
            cat_map = {
                "Forex": "hierarchy_v1.forex",
                "Indices": "hierarchy_v1.indices_group",
                "Commodities": "hierarchy_v1.commodities_group",
                "Crypto": "hierarchy_v1.crypto_currencies_group",
            }
            
            for cat, node_id in cat_map.items():
                try:
                    items = client.get_all_markets_from_node(node_id)
                    MARKET_CACHE[cat] = []
                    for m in items:
                        epic = m.get('epic')
                        # Simple Auto-Mapper Logic
                        yf = None
                        if cat == "Forex":
                             clean = epic.replace("/", "").replace("-", "")
                             if len(clean) == 6 or "CZK" in clean: yf = f"{clean}=X"
                        elif cat == "Crypto" and "USD" in epic:
                             yf = f"{epic.replace('USD', '')}-USD"
                        elif cat == "Commodities":
                             if "Gold" in epic: yf = "GC=F"
                             elif "Silver" in epic: yf = "SI=F"
                             elif "Oil" in epic: yf = "CL=F"
                        
                        if yf:
                            MARKET_CACHE[cat].append({'epic': epic, 'yf': yf})
                            
                    log(f"Loaded {len(MARKET_CACHE[cat])} items for {cat}")
                except Exception as ex:
                    log(f"Error loading {cat}: {ex}")

            # Hardcoded Stocks
            MARKET_CACHE["US Stocks"] = [
                {'epic': 'AAPL', 'yf': 'AAPL'}, {'epic': 'TSLA', 'yf': 'TSLA'}, 
                {'epic': 'NVDA', 'yf': 'NVDA'}, {'epic': 'MSFT', 'yf': 'MSFT'}
            ]

        # Flatten active categories into one watchlist
        for cat in active_cats:
            watchlist.extend(MARKET_CACHE.get(cat, []))

        log(f"Scanning {len(watchlist)} assets...")
        
        # 3. Scan & Execute
        trades_placed = 0
        
        # Limit scan to avoid Vercel timeout (max 10-15s typically for free tier)
        # In production, use async or split tasks. For now, scan first 30.
        for item in watchlist[:30]: 
            epic = item['epic']
            yf_ticker = item['yf']
            
            try:
                # Strategy Analysis
                strat = Strategy(yf_ticker)
                df = strat.fetch_data(period="1d", interval="5m")
                
                if df.empty:
                    continue
                    
                df = strat.calculate_indicators(df)
                result = strat.get_signal(df)
                
                action = result.get("action")
                rsi = result.get("rsi", 0)
                reason = result.get("reason", "")
                
                if action == "BUY":
                    log(f"🟢 BUY SIGNAL: {epic} (RSI {rsi:.2f})")
                    
                    # Check existing positions
                    positions = client.get_positions()
                    # Check if we already hold this epic
                    is_open = any(p.get('market', {}).get('epic') == epic for p in positions)
                    
                    if is_open:
                        log(f"Skipping {epic}: Already open.")
                    else:
                        # SIZE CALCULATION
                        # Forex 1 lot = 100k, so 0.1 is 10k.
                        # We need micro-lots.
                        size = 0.5 # Default CFD size
                        if "Forex" in active_cats and "USD" in epic:
                             size = 1000 # Example for Forex? No, Capital uses contracts.
                             # Capital.com Min size usually:
                             # Forex: 1000 (micro lot?) or 1?
                             # Let's stick to SAFE small number or check min size from API.
                             # Fallback to hardcoded small size for now.
                             size = 0.1 
                        
                        tp = result.get("tp")
                        sl = result.get("sl")
                        
                        resp = client.place_market_order(epic, size, direction="BUY", stop_loss=sl, take_profit=tp)
                        
                        if 'errorCode' in resp:
                            log(f"🔴 Order Rejected: {resp.get('errorCode')}")
                        else:
                            log(f"✅ Trade Executed: {epic} Ref: {resp.get('dealReference')}")
                            trades_placed += 1
                            
                elif rsi < 35: # Close call
                    log(f"👀 Watch: {epic} RSI {rsi:.2f} (Reason: {reason})")
                    
            except Exception as e:
                log(f"Error processing {epic}: {e}")
                
        log(f"Scan Complete. Trades: {trades_placed}")
        return {"status": "success", "trades": trades_placed}
        
    except Exception as e:
        log(f"🔥 Cron Critical Error: {e}")
        return {"status": "error", "error": str(e)}

# For local testing
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
