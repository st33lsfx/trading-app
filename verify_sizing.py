
import sys
import os

# Mock Client
class MockClient:
    def get_account_info(self):
        return {'accounts': [{'balance': {'balance': 2500.0}}]} # 2500 CZK Equity

    def get_instrument_info(self, epic):
        if "BTC" in epic:
            return {'min_size': 0.01, 'max_size': 100, 'step': 0.01}
        elif "EURUSD" in epic:
            return {'min_size': 1000, 'max_size': 1000000, 'step': 100}
        return {'min_size': 0.1, 'max_size': 10000, 'step': 0.1}

# Mock Bot Logic (simplified from bot.py)
class MockBot:
    def __init__(self):
        self.client = MockClient()
        self.trade_amount = 250.0  # Target Risk 250 CZK
        self.max_risk_pct = 0.15   # Max 15% equity (375 CZK)
        self._total_live_trades = 20 # Simulate experienced bot (full size)
        self.log_msgs = []

    def log(self, msg):
        self.log_msgs.append(msg)
        print(msg)

    def calculate_risk_based_size(self, epic, sl_distance, current_price, conversion=24.0):
        # 1. Get Equity
        equity = 2500.0
        
        # 2. Target Risk
        target_risk_czk = self.trade_amount
        if self._total_live_trades < 10:
             target_risk_czk = 100.0

        print(f"--- TEST: {epic} ---")
        print(f"Equity: {equity} CZK")
        print(f"Target Risk: {target_risk_czk} CZK")
        print(f"SL Distance: {sl_distance}")
        
        # 3. Risk Per Unit
        risk_per_unit = sl_distance * conversion
        print(f"Risk per Unit: {risk_per_unit:.2f} CZK")

        if risk_per_unit <= 0: return 0

        # 4. Raw Qty
        raw_qty = target_risk_czk / risk_per_unit
        print(f"Raw Qty: {raw_qty:.4f}")

        # 5. Constraints
        inst_info = self.client.get_instrument_info(epic)
        min_size = inst_info.get('min_size')
        
        if raw_qty < min_size:
            min_risk = min_size * risk_per_unit
            max_acc = equity * self.max_risk_pct
            print(f"Below Min Size ({min_size}). Min Risk: {min_risk:.2f} CZK. Cap: {max_acc:.2f} CZK")
            if min_risk > max_acc:
                print("SKIP: Too risky")
                return 0
            raw_qty = min_size

        # 6. Check Resulting Risk
        actual_risk = raw_qty * risk_per_unit
        print(f"FINAL QTY: {raw_qty}")
        print(f"ACTUAL RISK: {actual_risk:.2f} CZK")
        print(f"Risk %: {actual_risk/equity*100:.2f}%")
        return raw_qty

# RUN TESTS
bot = MockBot()

# Test 1: Crypto (BTC)
# Price 95000, SL 2% = 1900 USD distance
# Risk 250 CZK
# Conversion 24
# Risk per unit = 1900 * 24 = 45600 CZK
# Qty = 250 / 45600 = 0.0054
# Min size = 0.01
# Min risk = 0.01 * 45600 = 456 CZK
# Cap 15% = 375 CZK
# Result: 456 > 375 => SKIP? Or we allowed 15%?
# Wait, 15% of 2500 is 375. 456 is > 375. So it SHOULD SKIP if min size is too big.
# Let's see.
bot.calculate_risk_based_size("BTCUSD", 1900, 95000)

# Test 2: Forex (EURUSD)
# Price 1.0500, SL 0.6% = 0.0063 distance
# Risk 250 CZK
# Conversion 24 (USD base) or 26 (EUR)? EURUSD is USD quoted, value per pip is USD.
# 1 Lot (100,000) * 0.0063 = 630 USD risk = 15120 CZK risk.
# We want 250 CZK risk.
# Qty = 250 / (0.0063 * 24) = 250 / 0.1512 = 1653 units.
# Min size Capital = ?? Usually 1000 or 0.1 lot.
bot.calculate_risk_based_size("EURUSD", 0.0063, 1.0500)

