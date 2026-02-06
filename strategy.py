import yfinance as yf
import pandas as pd
import ta
import warnings
# Suppress FutureWarning from ta library regarding Series.__setitem__
# We filter by module 'ta' to be safe and cover all submodules
warnings.filterwarnings("ignore", category=FutureWarning, module="ta")

from datetime import datetime, timezone

class Strategy:
    def __init__(self, ticker):
        self.ticker = ticker

    def fetch_data(self, period="5d", interval="5m"):
        """Fetch historical data from Yahoo Finance."""
        try:
            ticker_obj = yf.Ticker(self.ticker)
            # Fetch enough data for 200 EMA + lookback
            df = ticker_obj.history(period=period, interval=interval)
            return df
        except Exception as e:
            print(f"Error fetching {self.ticker}: {e}")
            return pd.DataFrame()

    def fetch_trend_data(self):
        """Fetch 4h data for trend analysis."""
        try:
             # 1mo provides stable EMA50 for 4h timeframe (6 candles/day * 20 days = 120 candles)
            return self.fetch_data(period="1mo", interval="4h")
        except:
            return pd.DataFrame()

    def get_trend_direction(self, df_trend):
        """
        Determine higher-timeframe trend direction.
        Strategy: Price > EMA 50 = UP, Price < EMA 50 = DOWN
        """
        if df_trend.empty or len(df_trend) < 50:
            return "NEUTRAL"
        
        try:
            # Calculate EMA 50 on 4h data
            ema_50 = ta.trend.EMAIndicator(close=df_trend['Close'], window=50).ema_indicator()
            last_close = df_trend['Close'].iloc[-1]
            last_ema = ema_50.iloc[-1]
            
            if pd.isna(last_ema):
                return "NEUTRAL"
                
            return "UP" if last_close > last_ema else "DOWN"
        except Exception as e:
            print(f"Trend calc error: {e}")
            return "NEUTRAL"

    def calculate_indicators(self, df):
        """Calculate Top Scalping Indicators using 'ta' library."""
        if df.empty: return df

        try:
            # 1. EMA 200 (Trend Filter)
            ema_200 = ta.trend.EMAIndicator(close=df['Close'], window=200)
            df['EMA_200'] = ema_200.ema_indicator()

            # 2. SMA 20 (Short-term Momentum)
            sma_20 = ta.trend.SMAIndicator(close=df['Close'], window=20)
            df['SMA_20'] = sma_20.sma_indicator()

            # 3. RSI 14
            rsi = ta.momentum.RSIIndicator(close=df['Close'], window=14)
            df['RSI'] = rsi.rsi()

            # 4. MACD (12, 26, 9)
            macd_obj = ta.trend.MACD(close=df['Close'], window_slow=26, window_fast=12, window_sign=9)
            df['MACD'] = macd_obj.macd()
            df['MACD_SIGNAL'] = macd_obj.macd_signal()
            df['MACD_HIST'] = macd_obj.macd_diff()

            # 5. Stochastic (14, 3, 3)
            stoch = ta.momentum.StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'], window=14, smooth_window=3)
            df['STOCH_K'] = stoch.stoch()
            df['STOCH_D'] = stoch.stoch_signal()

            # 6. Parabolic SAR
            psar = ta.trend.PSARIndicator(high=df['High'], low=df['Low'], close=df['Close'], step=0.02, max_step=0.2)
            df['PSAR'] = psar.psar()

            # 7. ADX (Trend Strength)
            adx = ta.trend.ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14)
            df['ADX'] = adx.adx()
            df['DI_PLUS'] = adx.adx_pos()
            df['DI_MINUS'] = adx.adx_neg()

            # 8. MA Ribbon (Scalping: 5, 8, 13 EMA)
            df['EMA_5'] = ta.trend.EMAIndicator(close=df['Close'], window=5).ema_indicator()
            df['EMA_8'] = ta.trend.EMAIndicator(close=df['Close'], window=8).ema_indicator()
            df['EMA_13'] = ta.trend.EMAIndicator(close=df['Close'], window=13).ema_indicator()
            df['EMA_50'] = ta.trend.EMAIndicator(close=df['Close'], window=50).ema_indicator()

            # 9. Volume SMA (Confirmation)
            df['VOL_SMA_20'] = ta.trend.SMAIndicator(close=df['Volume'], window=20).sma_indicator()

            # 10. Recent Swing Low/High (for SL)
            df['SWING_LOW'] = df['Low'].rolling(window=5).min()
            df['SWING_HIGH'] = df['High'].rolling(window=5).max()

            # 11. ATR 14 (Scalping: volatility-based SL/TP)
            atr = ta.volatility.AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=14)
            df['ATR'] = atr.average_true_range()

            # 12. Bollinger Bands (for mean reversion)
            bb = ta.volatility.BollingerBands(close=df['Close'], window=20, window_dev=2)
            df['BB_UPPER'] = bb.bollinger_hband()
            df['BB_LOWER'] = bb.bollinger_lband()
            df['BB_MID'] = bb.bollinger_mavg()

            # 13. Market Structure (Higher Highs / Lower Lows)
            df['PREV_HIGH'] = df['High'].shift(1)
            df['PREV_LOW'] = df['Low'].shift(1)
            df['HH'] = df['High'] > df['High'].rolling(window=10).max().shift(1)  # Higher High
            df['LL'] = df['Low'] < df['Low'].rolling(window=10).min().shift(1)    # Lower Low

        except Exception as e:
            print(f"Indicator Error: {e}")

        return df

    def is_session_active(self, df):
        """
        Check if current time is in optimal trading session.
        Best scalping sessions:
        - London Open: 08:00-11:00 UTC
        - NY Open: 13:00-16:00 UTC
        - London/NY Overlap: 13:00-16:00 UTC (BEST)
        """
        try:
            if df.empty:
                return False, "No data"

            # Get last candle timestamp
            last_time = df.index[-1]

            # Convert to UTC if timezone aware
            if hasattr(last_time, 'tz') and last_time.tz is not None:
                utc_hour = last_time.astimezone(timezone.utc).hour
            else:
                # Assume UTC
                utc_hour = last_time.hour

            # Define sessions
            london_open = 8 <= utc_hour < 11
            ny_open = 13 <= utc_hour < 16
            overlap = 13 <= utc_hour < 16
            asian_session = 0 <= utc_hour < 8

            if overlap:
                return True, "London/NY Overlap (Best)"
            elif london_open:
                return True, "London Open"
            elif ny_open:
                return True, "NY Open"
            elif asian_session:
                return False, "Asian Session (Low Volatility)"
            else:
                return False, "Off-Hours"

        except Exception as e:
            return True, f"Session check error: {e}"

    def check_volume_confirmation(self, df):
        """
        Check if volume confirms the move.
        Returns True if volume is above average.
        """
        if df.empty or 'Volume' not in df.columns:
            return True, 1.0  # No volume data, skip filter

        last = df.iloc[-1]
        vol = last.get('Volume', 0)
        vol_avg = last.get('VOL_SMA_20', 0)

        if vol_avg > 0:
            vol_ratio = vol / vol_avg
            return vol_ratio > 0.8, vol_ratio  # At least 80% of average

        return True, 1.0

    def check_market_structure(self, df, direction="BUY"):
        """
        Check market structure for entry confirmation.
        BUY: Look for higher lows (bullish structure)
        SELL: Look for lower highs (bearish structure)
        """
        if len(df) < 15:
            return True, "Not enough data"

        recent = df.tail(10)

        if direction == "BUY":
            # Check for higher lows (bullish)
            lows = recent['Low'].values
            higher_lows = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i-1])
            bullish = higher_lows >= 4  # At least 4 out of 9 comparisons
            return bullish, f"Higher Lows: {higher_lows}/9"
        else:
            # Check for lower highs (bearish)
            highs = recent['High'].values
            lower_highs = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i-1])
            bearish = lower_highs >= 4
            return bearish, f"Lower Highs: {lower_highs}/9"

    def get_signal(self, df, config=None):
        """
        Enhanced Scalping Strategy with SHORT support.
        Uses config dict for thresholds if provided.
        """
        if config is None:
            config = {
                "rsi_buy": 58,
                "rsi_oversold": 38,
                "rsi_sell": 42,
                "rsi_overbought": 62,
                "adx_min": 28,
                "risk_reward": 1.8,
                "atr_sl_mult": 1.5,
                "max_risk_pct": 0.006,
                "require_volume": True,
                "require_session": True,
                "enable_shorts": True
            }

        if df.empty or 'EMA_200' not in df.columns or 'PSAR' not in df.columns:
             return {"action": "NEUTRAL", "reason": "Not enough data"}

        # Thresholds
        RSI_BUY_MAX = config.get('rsi_buy', 58)
        RSI_OVERSOLD = config.get('rsi_oversold', 38)
        RSI_SELL_MIN = config.get('rsi_sell', 42)
        RSI_OVERBOUGHT = config.get('rsi_overbought', 62)
        ADX_MIN = config.get('adx_min', 28)
        RISK_REWARD = config.get('risk_reward', 1.8)
        ATR_SL_MULT = config.get('atr_sl_mult', 1.5)
        MAX_RISK_PCT = config.get('max_risk_pct', 0.006)
        REQUIRE_VOLUME = config.get('require_volume', True)
        REQUIRE_SESSION = config.get('require_session', True)
        ENABLE_SHORTS = config.get('enable_shorts', True)

        last = df.iloc[-1]
        close = last['Close']
        ema_200 = last.get('EMA_200', 0)
        ema_50 = last.get('EMA_50', 0)
        psar = last.get('PSAR', 0)
        rsi = last.get('RSI', 50)
        stoch_k = last.get('STOCH_K', 50)
        macd_hist = last.get('MACD_HIST', 0)
        adx = last.get('ADX', 0)
        di_plus = last.get('DI_PLUS', 0)
        di_minus = last.get('DI_MINUS', 0)
        atr_val = last.get('ATR', 0)

        # ===== SESSION FILTER =====
        if REQUIRE_SESSION:
            session_ok, session_reason = self.is_session_active(df)
            if not session_ok:
                return {"action": "NEUTRAL", "reason": f"Session: {session_reason}", "rsi": rsi}

        # ===== VOLUME FILTER =====
        if REQUIRE_VOLUME:
            vol_ok, vol_ratio = self.check_volume_confirmation(df)
            if not vol_ok:
                return {"action": "NEUTRAL", "reason": f"Low volume ({vol_ratio:.1f}x avg)", "rsi": rsi}

        # ===== TREND STRENGTH FILTER =====
        if adx < ADX_MIN:
            return {"action": "NEUTRAL", "reason": f"Weak Trend (ADX {adx:.1f} < {ADX_MIN})", "rsi": rsi}

        # ===== DETERMINE TREND DIRECTION =====
        is_uptrend = close > ema_200 and di_plus > di_minus
        is_downtrend = close < ema_200 and di_minus > di_plus

        # MA Ribbon alignment
        ema_5 = last.get('EMA_5', 0)
        ema_8 = last.get('EMA_8', 0)
        ema_13 = last.get('EMA_13', 0)
        ribbon_bullish = close > ema_5 > ema_8 > ema_13
        ribbon_bearish = close < ema_5 < ema_8 < ema_13

        # ===== LONG ENTRY LOGIC =====
        if is_uptrend and close > psar:
            # Market structure check
            structure_ok, structure_reason = self.check_market_structure(df, "BUY")

            # Momentum conditions
            is_momentum_buy = macd_hist > 0 and rsi < RSI_BUY_MAX
            is_oversold_bounce = (rsi < RSI_OVERSOLD or stoch_k < 20) and macd_hist > -0.001

            if (is_momentum_buy and ribbon_bullish) or is_oversold_bounce:
                if structure_ok or is_oversold_bounce:
                    # Calculate SL/TP
                    sl, tp = self._calculate_sl_tp(close, atr_val, ATR_SL_MULT, MAX_RISK_PCT, RISK_REWARD, "BUY", last)

                    reason = "Ribbon Long" if ribbon_bullish else "Oversold Bounce"
                    if structure_ok:
                        reason += f" + {structure_reason}"

                    return {
                        "action": "BUY",
                        "tp": tp,
                        "sl": sl,
                        "rsi": rsi,
                        "reason": reason
                    }

        # ===== SHORT ENTRY LOGIC =====
        if ENABLE_SHORTS and is_downtrend and close < psar:
            # Market structure check
            structure_ok, structure_reason = self.check_market_structure(df, "SELL")

            # Momentum conditions for short
            is_momentum_sell = macd_hist < 0 and rsi > RSI_SELL_MIN
            is_overbought_drop = (rsi > RSI_OVERBOUGHT or stoch_k > 80) and macd_hist < 0.001

            if (is_momentum_sell and ribbon_bearish) or is_overbought_drop:
                if structure_ok or is_overbought_drop:
                    # Calculate SL/TP for SHORT
                    sl, tp = self._calculate_sl_tp(close, atr_val, ATR_SL_MULT, MAX_RISK_PCT, RISK_REWARD, "SELL", last)

                    reason = "Ribbon Short" if ribbon_bearish else "Overbought Drop"
                    if structure_ok:
                        reason += f" + {structure_reason}"

                    return {
                        "action": "SELL",
                        "tp": tp,
                        "sl": sl,
                        "rsi": rsi,
                        "reason": reason
                    }

        # No signal
        trend_status = "Uptrend" if is_uptrend else ("Downtrend" if is_downtrend else "Ranging")
        return {"action": "NEUTRAL", "reason": f"Waiting ({trend_status})", "rsi": rsi}

    def _calculate_sl_tp(self, close, atr_val, atr_mult, max_risk_pct, risk_reward, direction, last):
        """Calculate Stop Loss and Take Profit levels.
        
        For Forex (price ~1.0-150): min 0.5% SL = 50+ pips
        For Crypto/Stocks: min 0.8% SL
        """

        if pd.notna(atr_val) and atr_val > 0:
            sl_distance = atr_val * atr_mult

            # Cap risk at max_risk_pct
            max_sl_distance = close * max_risk_pct
            if sl_distance > max_sl_distance:
                sl_distance = max_sl_distance

            # Minimum SL based on asset type
            # Forex pairs (price 0.5-2.0): min 0.5% = ~50-80 pips
            # JPY pairs (price 100-150): min 0.3% = ~30-50 pips  
            # Crypto/Stocks: min 0.8%
            if close < 3:  # Forex (EURUSD ~1.08, AUDNZD ~1.16)
                min_risk = 0.005  # 0.5% = ~50+ pips
            elif close < 200:  # JPY pairs, cheap stocks
                min_risk = 0.004  # 0.4%
            else:  # Crypto, expensive stocks
                min_risk = 0.008  # 0.8%
            
            if sl_distance / close < min_risk:
                sl_distance = close * min_risk
                
            # Ceiling: max 2% risk
            if sl_distance / close > 0.02:
                sl_distance = close * 0.02
        else:
            sl_distance = close * 0.008  # Default 0.8%

        if direction == "BUY":
            sl = close - sl_distance
            tp = close + (sl_distance * risk_reward)
        else:  # SELL
            sl = close + sl_distance
            tp = close - (sl_distance * risk_reward)

        # Round to appropriate decimals (5 for Forex, 2 for stocks)
        if close < 10:
            decimals = 5
        elif close < 1000:
            decimals = 2
        else:
            decimals = 1

        return round(sl, decimals), round(tp, decimals)
