
import pandas as pd
import numpy as np

class SmartZones:
    def __init__(self, window=5):
        """
        :param window: Window for fractal detection (default 5 bars)
        """
        self.window = window
        self.zones = [] # List of {'price': float, 'type': 'SUP'|'RES', 'created_at': datetime}

    def _detect_fractals(self, df):
        """
        Identifies Bill Williams Fractals (5-bar High/Low).
        """
        df['is_high'] = df['High'].rolling(window=self.window, center=True).max() == df['High']
        df['is_low'] = df['Low'].rolling(window=self.window, center=True).min() == df['Low']
        return df

    def update_zones(self, df, lookback=100):
        """
        Updates active AOI zones based on recent fractals.
        Keeps only fresh zones from the last 'lookback' bars.
        """
        df = self._detect_fractals(df.copy())
        
        # Clear old zones
        self.zones = []
        
        # Scan recent history
        subset = df.iloc[-lookback:]
        
        for idx, row in subset.iterrows():
            if row['is_high']:
                self.zones.append({'price': row['High'], 'type': 'RES', 'time': idx})
            if row['is_low']:
                self.zones.append({'price': row['Low'], 'type': 'SUP', 'time': idx})
        
        # Merge close zones? (Optional optimization)
        return self.zones

    def find_nearest_zone(self, price, z_type, tolerance=0.002):
        """
        Finds if price is within an AOI.
        """
        for zone in self.zones:
            if zone['type'] != z_type: continue
            
            # Check proximity (e.g. 0.2% range)
            upper = zone['price'] * (1 + tolerance)
            lower = zone['price'] * (1 - tolerance)
            
            if lower <= price <= upper:
                return zone
        return None

    def check_setup(self, df):
        """
        Checks for 2H (Lower High) or 2L (Higher Low) setup near AOIs.
        Returns: 'BUY', 'SELL', or None
        """
        if len(df) < 5: return None
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 1. Update Zones (Dynamic)
        self.update_zones(df)
        
        # 2. Identify Structure
        # 2L (Higher Low) -> Bullish Reversal
        # Condition: 
        # a) Current is a Fractal Low (or potential swing low)
        # b) Current Low > Previous Swing Low (Higher Low)
        # c) Previous Swing Low was touching a SUP AOI
        
        # We need the last 2 swing lows
        swings_low = [z for z in self.zones if z['type'] == 'SUP']
        swings_high = [z for z in self.zones if z['type'] == 'RES']
        
        if len(swings_low) < 2: return None
        
        # Last swing (potential 2L)
        last_s_low = swings_low[-1] 
        prev_s_low = swings_low[-2]
        
        # Last swing (potential 2H)
        if len(swings_high) >= 2:
            last_s_high = swings_high[-1]
            prev_s_high = swings_high[-2]
            
            # --- 2H SETUP (SELL) ---
            # Logic: We just formed a Lower High (2H)
            # And the previous High was at Resistance (AOI)
            if last_s_high['price'] < prev_s_high['price']:
                # Check if Prev High interacted with older Resistance?
                # Simplified: Just identifying the Lower High formation is the signal
                # Trigger: Price breaks below the mini-low between the highs? (Choch)
                # Or aggressive: Enter at close of the fractal confirmation candle?
                
                # Let's use simple Swing Failure Pattern logic
                # If we formed a fractal high LOWER than previous fractal high
                if last_s_high['time'] == df.index[-2]: # Confirmed recently (rolling window lag)
                     return 'SELL', f"2H Detected (LH: {last_s_high['price']:.4f} < {prev_s_high['price']:.4f})"

        # --- 2L SETUP (BUY) ---
        if len(swings_low) >= 2:
            last_s_low = swings_low[-1]
            prev_s_low = swings_low[-2]
            
            # Logic: Higher Low (2L)
            if last_s_low['price'] > prev_s_low['price']:
                 if last_s_low['time'] == df.index[-2]:
                     return 'BUY', f"2L Detected (HL: {last_s_low['price']:.4f} > {prev_s_low['price']:.4f})"

        return None, None
