# 🦅 Ultimate Trading Bot v2.0

Professional-grade mean reversion trading bot with Multi-Timeframe analysis, Telegram notifications, and smart risk management.

## 🚀 Key Features

### 🧠 Smart Strategy

- **Mean Reversion**: Capitalizes on overextended price moves (RSI + Bollinger Bands).
- **Multi-Timeframe Analysis**: Trades ONLY in the direction of the 4H trend (EMA 50).
- **Filters**: Volatility, ADX (Trend Strength), Session (London/NY), and R:R checks.

### 🛡️ Risk Management

- **Trailing Stop**:
  - Moves SL to Break Even after 1.0 ATR profit.
  - Locks +0.5 ATR profit after 1.5 ATR gain.
- **Dynamic Position Sizing**: Based on account balance and risk % (default 0.5% - 2%).
- **Daily Limits**: Max daily loss and profit targets.

### ⚡ Technology

- **Scanner**: Real-time dashboard scanning 40+ assets every 30s.
- **Telegram**: Instant notifications for trades and daily summaries.
- **Streamlit UI**: controlling the bot, visualizing equity curve, and analyzing performance.

## 🛠️ Setup

1. **Install Dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

2. **Run the App**:

   ```bash
   streamlit run streamlit_app.py
   ```

3. **Configure**:
   - Enter **Telegram Bot Token** & **Chat ID** in the Sidebar.
   - Select Broker (Capital.com / Trading 212).
   - Start the Bot!

## 📊 Strategy Logic

1. **Wait for Setup**: Price touches Outer Bollinger Band + Extreme RSI (<38 / >62).
2. **Check Trend**: Is 4H Trend Aligned? (Price > EMA50 for Buy).
3. **Execute**: Place Market Order with Hard SL (2.0 ATR) and TP (4.0 ATR).
4. **Manage**: Monitor every 5s. Trail SL to lock profits.

## 📂 Project Structure

- `streamlit_app.py`: Main Dashboard UI.
- `bot.py`: Core logic loop, scanning, and position management.
- `mean_reversion_strategy.py`: Signal generation and filter logic.
- `telegram_notifier.py`: Notification system.
- `capital_client.py`: API Wrapper for Capital.com.

---

_Disclaimer: Trading involves risk. Use at your own risk._
