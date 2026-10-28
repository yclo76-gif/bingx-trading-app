import pandas as pd
import numpy as np
import ccxt

class TradingStrategyEngine:
    def __init__(self, symbol='BTC/USDT:USDT', timeframe='1h'):
        self.symbol = symbol
        self.timeframe = timeframe
        self.exchange = ccxt.bingx({'enableRateLimit': True})

    def fetch_ohlcv(self, limit=100):
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe=self.timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"獲取資料失敗: {e}")
            return None

    def calculate_vegas_tunnel(self, df):
        # Vegas 隧道：快線組 (EMA 144, 169), 慢線組 (EMA 576, 676)
        df['ema_144'] = df['close'].ewm(span=144, adjust=False).mean()
        df['ema_169'] = df['close'].ewm(span=169, adjust=False).mean()
        df['ema_576'] = df['close'].ewm(span=576, adjust=False).mean()
        df['ema_676'] = df['close'].ewm(span=676, adjust=False).mean()
        return df

    def calculate_fractals(self, df, n=2):
        # 簡易威廉分形 (Fractal) 計算高低點
        df['fractal_high'] = np.nan
        df['fractal_low'] = np.nan
        
        for i in range(n, len(df) - n):
            # 頂分形
            if df['high'].iloc[i] == max(df['high'].iloc[i-n:i+n+1]):
                df.loc[df.index[i], 'fractal_high'] = df['high'].iloc[i]
            # 底分形
            if df['low'].iloc[i] == min(df['low'].iloc[i-n:i+n+1]):
                df.loc[df.index[i], 'fractal_low'] = df['low'].iloc[i]
                
        return df

    def analyze_market(self):
        df = self.fetch_ohlcv(limit=300)
        if df is None or df.empty:
            return None
        
        df = self.calculate_vegas_tunnel(df)
        df = self.calculate_fractals(df)
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 判斷 Vegas 趨勢
        fast_ema_top = max(latest['ema_144'], latest['ema_169'])
        fast_ema_bot = min(latest['ema_144'], latest['ema_169'])
        slow_ema_top = max(latest['ema_576'], latest['ema_676'])
        
        trend = "盤整震盪"
        if latest['close'] > fast_ema_top and fast_ema_top > slow_ema_top:
            trend = "多頭趨勢 (Bullish)"
        elif latest['close'] < fast_ema_bot and fast_ema_bot < slow_ema_top:
            trend = "空頭趨勢 (Bearish)"
            
        # 計算建議進場、止損、止盈點位
        close_price = latest['close']
        atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
        
        if "空頭" in trend:
            signal = "尋找機會做空 (Short)"
            suggested_entry = close_price
            stop_loss = round(close_price + (atr * 1.5), 2)
            take_profit_1 = round(close_price - (atr * 1.5), 2)
            take_profit_2 = round(close_price - (atr * 3.0), 2)
        elif "多頭" in trend:
            signal = "尋找機會做多 (Long)"
            suggested_entry = close_price
            stop_loss = round(close_price - (atr * 1.5), 2)
            take_profit_1 = round(close_price + (atr * 1.5), 2)
            take_profit_2 = round(close_price + (atr * 3.0), 2)
        else:
            signal = "觀望中 (Sideway)"
            suggested_entry = close_price
            stop_loss = round(close_price - atr, 2)
            take_profit_1 = round(close_price + atr, 2)
            take_profit_2 = round(close_price + (atr * 2), 2)

        result = {
            "timestamp": latest['timestamp'],
            "close": close_price,
            "trend": trend,
            "signal": signal,
            "entry": suggested_entry,
            "sl": stop_loss,
            "tp1": take_profit_1,
            "tp2": take_profit_2,
            "dataframe": df
        }
        return result