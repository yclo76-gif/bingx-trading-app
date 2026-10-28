import pandas as pd
import numpy as np
import ccxt

class TradingStrategyEngine:
    def __init__(self, symbol='BTC/USDT:USDT', timeframe='15m'):
        self.symbol = symbol
        self.timeframe = timeframe
        self.exchange = ccxt.bingx({'enableRateLimit': True})

    def fetch_ohlcv(self, limit=120):
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe=self.timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            return None

    def calculate_vegas_tunnel(self, df):
        df['ema_144'] = df['close'].ewm(span=144, adjust=False).mean()
        df['ema_169'] = df['close'].ewm(span=169, adjust=False).mean()
        df['ema_576'] = df['close'].ewm(span=576, adjust=False).mean()
        df['ema_676'] = df['close'].ewm(span=676, adjust=False).mean()
        return df

    def analyze_market(self):
        df = self.fetch_ohlcv(limit=120)
        if df is None or df.empty:
            return None
        
        df = self.calculate_vegas_tunnel(df)
        latest = df.iloc[-1]
        
        fast_ema_top = max(latest['ema_144'], latest['ema_169'])
        fast_ema_bot = min(latest['ema_144'], latest['ema_169'])
        slow_ema_top = max(latest['ema_576'], latest['ema_676'])
        slow_ema_bot = min(latest['ema_576'], latest['ema_676'])
        
        # 計算通道擴張率（短線爆發強度）
        tunnel_spread = abs(fast_ema_top - slow_ema_top) / slow_ema_top * 100

        trend = "盤整震盪"
        est_win_rate = 52.0
        
        # 短線趨勢與勝率評估邏輯
        if latest['close'] > fast_ema_top and fast_ema_top > slow_ema_top and tunnel_spread > 0.4:
            trend = "多頭強勢趨勢 (Bullish)"
