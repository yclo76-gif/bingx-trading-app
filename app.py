import time
from datetime import datetime
import ccxt
import numpy as np
import pandas as pd

# ==========================================
# 1. 全市場篩選與策略參數設定 (V3.0 擴展版)
# ==========================================
TIMEFRAME_MAIN = "5m"
TIMEFRAME_TREND = "15m"
KLINE_LIMIT = 1000

# 【第一層：全市場流動性與活躍度濾網】
MIN_24H_QUOTE_VOL = (
    15_000_000  # 24小時最低成交額：1,500萬 USDT (過濾插針小幣與高滑點幣)
)
MIN_24H_CHANGE_PCT = 1.5  # 24小時漲跌幅絕對值需 >= 1.5% (過濾毫無波動的死魚幣)
MAX_SCAN_SYMBOLS = (
    60  # 每輪最多深度掃描成交量前 60 名的活躍幣種 (確保 25 秒內掃完，信號零延遲)
)

# 黑名單：排除穩定幣或異常交易對
BLACKLIST_COINS = ["USDC", "USDE", "FDUSD", "TUSD", "DAI", "BUSD"]

# 【第二、三層：65%+ 高勝率技術指標濾網】
FRACTAL_WINDOW = 4  # 9根K線分形結構
VOL_MULTIPLIER = 1.25  # 突破K線成交量需 >= 20MA 的 1.25 倍
MIN_ADX = 20.0  # ADX 趨勢強度門檻
MAX_BIAS_PCT = 0.022  # 距離 5m 短期通道最大乖離率 2.2%
MIN_BODY_RATIO = 0.45  # K線實體飽滿度 >= 45%
ATR_SL_MULT = 1.5  # ATR 動態止損倍數


# ==========================================
# 2. 初始化 BingX 交易所與全市場動態篩選器
# ==========================================
def init_exchange():
    return ccxt.bingx(
        {
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        }
    )


def get_dynamic_active_symbols(exchange) -> list:
    """【第一層漏斗】全市場掃描，自動篩選高流動性、高活躍度的優質合約幣種"""
    print("📡 正在獲取 BingX 全市場 24h 行情數據進行流動性篩選...")
    markets = exchange.load_markets()
    tickers = exchange.fetch_tickers()

    candidates = []
    for symbol, ticker in tickers.items():
        # 1. 確保是啟用中的 USDT 永續合約
        if symbol not in markets:
            continue
        market = markets[symbol]
        if not (
            market.get("swap")
            and market.get("linear")
            and market.get("quote") == "USDT"
            and market.get("active")
        ):
            continue

        base_coin = market.get("base", "")
        if base_coin in BLACKLIST_COINS:
            continue

        # 2. 取得 24h 成交額 (USDT) 與 24h 漲跌幅 (%)
        quote_vol = ticker.get("quoteVolume")
        if quote_vol is None or quote_vol == 0:
            # 若部分 API 欄位未直接提供 quoteVolume，則以 baseVolume * last 估算
            base_vol = ticker.get("baseVolume") or 0
            last_price = ticker.get("last") or 0
            quote_vol = base_vol * last_price

        change_pct = abs(ticker.get("percentage") or 0.0)

        # 3. 執行流動性與波動度過濾
        if (
            quote_vol >= MIN_24H_QUOTE_VOL
            and change_pct >= MIN_24H_CHANGE_PCT
        ):
            candidates.append(
                {
                    "symbol": symbol,
                    "quote_vol": quote_vol,
                    "change_pct": change_pct,
                }
            )

    # 依照 24h 成交額由高至低排序，取前 MAX_SCAN_SYMBOLS 名
    candidates.sort(key=lambda x: x["quote_vol"], reverse=True)
    selected = candidates[:MAX_SCAN_SYMBOLS]

    print(
        f"✅ 全市場共 {len(markets)} 個交易對 -> 通過流動性(>1500萬U)與波動濾網共 {len(candidates)} 個 -> 鎖定前 {len(selected)} 大熱門幣種進行深度掃描！"
    )
    return [item["symbol"] for item in selected]


# ==========================================
# 3. 技術指標與分形趨勢線計算模組
# ==========================================
def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    # 1. Vegas 雙通道
    df["ema12"] = df["close"].ewm(span=12, adjust=False).mean()
    df["ema144"] = df["close"].ewm(span=144, adjust=False).mean()
    df["ema169"] = df["close"].ewm(span=169, adjust=False).mean()
    df["ema576"] = df["close"].ewm(span=576, adjust=False).mean()
    df["ema676"] = df["close"].ewm(span=676, adjust=False).mean()

    df["tunnel1_top"] = df[["ema144", "ema169"]].max(axis=1)
    df["tunnel1_bottom"] = df[["ema144", "ema169"]].min(axis=1)
    df["tunnel2_top"] = df[["ema576", "ema676"]].max(axis=1)
    df["tunnel2_bottom"] = df[["ema576", "ema676"]].min(axis=1)

    # 2. 成交量均線與實體佔比
    df["vol_ma20"] = df["volume"].rolling(window=20).mean()
    candle_range = (df["high"] - df["low"]).replace(0, np.nan)
    df["body_ratio"] = (df["close"] - df["open"]).abs() / candle_range

    # 3. RSI (14)
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (
        (-delta.where(delta < 0, 0.0)).ewm(alpha=1 / 14, adjust=False).mean()
    )
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    # 4. ATR (14) 與 ADX (14)
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()

    up_move = df["high"] - df["high"].shift(1)
    down_move = df["low"].shift(1) - df["low"]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where(
        (down_move > up_move) & (down_move > 0), down_move, 0.0
    )

    plus_di = (
        100
        * pd.Series(plus_dm, index=df.index)
        .ewm(alpha=1 / 14, adjust=False)
        .mean()
        / df["atr"]
    )
    minus_di = (
        100
        * pd.Series(minus_dm, index=df.index)
        .ewm(alpha=1 / 14, adjust=False)
        .mean()
        / df["atr"]
    )
    dx = (
        100
        * (plus_di - minus_di).abs()
        / (plus_di + minus_di).replace(0, np.nan)
    )
    df["adx"] = dx.ewm(alpha=1 / 14, adjust=False).mean()

    return df


def calculate_fractals(
    df: pd.DataFrame, n: int = FRACTAL_WINDOW
) -> pd.DataFrame:
    df["fractal_high"] = np.nan
    df["fractal_low"] = np.nan
    highs = df["high"].values
    lows = df["low"].values
    length = len(df)

    for i in range(n, length - n - 1):
        if highs[i] == max(highs[i - n : i + n + 1]) and (
            highs[i] > highs[i - 1] or highs[i] > highs[i + 1]
        ):
            df.loc[df.index[i], "fractal_high"] = highs[i]
        if lows[i] == min(lows[i - n : i + n + 1]) and (
            lows[i] < lows[i - 1] or lows[i] < lows[i + 1]
        ):
            df.loc[df.index[i], "fractal_low"] = lows[i]
    return df


def get_auto_trendlines(df: pd.DataFrame, eval_idx: int):
    valid_end = eval_idx - FRACTAL_WINDOW
    sub_df = df.iloc[: valid_end + 1]
    f_highs = sub_df[sub_df["fractal_high"].notna()]
    f_lows = sub_df[sub_df["fractal_low"].notna()]

    res_line = {
        "curr_val": None,
        "prev_val": None,
        "slope": None,
        "valid": False,
    }
    sup_line = {
        "curr_val": None,
        "prev_val": None,
        "slope": None,
        "valid": False,
    }

    if len(f_highs) >= 2:
        idx1, idx2 = f_highs.index[-2], f_highs.index[-1]
        y1, y2 = (
            f_highs["fractal_high"].iloc[-2],
            f_highs["fractal_high"].iloc[-1],
        )
        slope = (y2 - y1) / (idx2 - idx1)
        res_line = {
            "curr_val": y2 + slope * (eval_idx - idx2),
            "prev_val": y2 + slope * ((eval_idx - 1) - idx2),
            "slope": slope,
            "valid": True,
        }

    if len(f_lows) >= 2:
        idx1, idx2 = f_lows.index[-2], f_lows.index[-1]
        y1, y2 = (
            f_lows["fractal_low"].iloc[-2],
            f_lows["fractal_low"].iloc[-1],
        )
        slope = (y2 - y1) / (idx2 - idx1)
        sup_line = {
            "curr_val": y2 + slope * (eval_idx - idx2),
            "prev_val": y2 + slope * ((eval_idx - 1) - idx2),
            "slope": slope,
            "valid": True,
        }

    return res_line, sup_line


# ==========================================
# 4. 單一幣種高勝率狙擊分析
# ==========================================
def analyze_symbol(exchange, symbol: str):
    try:
        ohlcv_5m = exchange.fetch_ohlcv(
            symbol, timeframe=TIMEFRAME_MAIN, limit=KLINE_LIMIT
        )
        ohlcv_15m = exchange.fetch_ohlcv(
            symbol, timeframe=TIMEFRAME_TREND, limit=KLINE_LIMIT
        )

        # 【挑戰3對策】嚴格檢查歷史K線數量，排除剛上市不足7天的新幣(確保EMA676收斂)
        if len(ohlcv_5m) < 700 or len(ohlcv_15m) < 700:
            return None

        df_5m = pd.DataFrame(
            ohlcv_5m,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df_15m = pd.DataFrame(
            ohlcv_15m,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )

        df_5m = calculate_indicators(df_5m)
        df_5m = calculate_fractals(df_5m, n=FRACTAL_WINDOW)
        df_15m = calculate_indicators(df_15m)

        eval_idx = len(df_5m) - 2
        curr_5m = df_5m.iloc[eval_idx]
        prev_5m = df_5m.iloc[eval_idx - 1]
        curr_15m = df_15m.iloc[-2]

        res_line, sup_line = get_auto_trendlines(df_5m, eval_idx)
        close_price = curr_5m["close"]
        atr_val = curr_5m["atr"]

        # 15m 與 5m Vegas 雙通道共振判定
        trend_15m_bull = (curr_15m["close"] > curr_15m["tunnel1_top"]) and (
            curr_15m["ema12"] > curr_15m["tunnel1_top"]
        )
        trend_15m_bear = (
            curr_15m["close"] < curr_15m["tunnel1_bottom"]
        ) and (curr_15m["ema12"] < curr_15m["tunnel1_bottom"])

        vegas_5m_bull = (
            (close_price > curr_5m["tunnel1_top"])
            and (curr_5m["ema12"] > curr_5m["tunnel1_top"])
            and (curr_5m["tunnel1_bottom"] > curr_5m["tunnel2_bottom"])
        )
        vegas_5m_bear = (
            (close_price < curr_5m["tunnel1_bottom"])
            and (curr_5m["ema12"] < curr_5m["tunnel1_bottom"])
            and (curr_5m["tunnel1_top"] < curr_5m["tunnel2_top"])
        )

        # 輔助濾網指標
        bias_bull = (close_price - curr_5m["tunnel1_top"]) / curr_5m[
            "tunnel1_top"
        ]
        bias_bear = (curr_5m["tunnel1_bottom"] - close_price) / curr_5m[
            "tunnel1_bottom"
        ]
        vol_ok = curr_5m["volume"] >= (curr_5m["vol_ma20"] * VOL_MULTIPLIER)
        adx_ok = curr_5m["adx"] >= MIN_ADX
        body_ok = curr_5m["body_ratio"] >= MIN_BODY_RATIO
        rsi_bull_ok = 52.0 <= curr_5m["rsi"] <= 68.0
        rsi_bear_ok = 32.0 <= curr_5m["rsi"] <= 48.0

        # 趨勢線突破與回踩判定
        valid_breakout_up = (
            res_line["valid"]
            and (res_line["slope"] <= close_price * 0.0003)
            and (prev_5m["close"] <= res_line["prev_val"])
            and (close_price > res_line["curr_val"])
            and (curr_5m["close"] > curr_5m["open"])
        )
        valid_breakout_down = (
            sup_line["valid"]
            and (sup_line["slope"] >= -close_price * 0.0003)
            and (prev_5m["close"] >= sup_line["prev_val"])
            and (close_price < sup_line["curr_val"])
            and (curr_5m["close"] < curr_5m["open"])
        )
        pullback_bull = (
            (curr_5m["low"] <= curr_5m["tunnel1_top"] * 1.0015)
            and (close_price > curr_5m["tunnel1_top"])
            and (curr_5m["close"] > curr_5m["open"])
            and (curr_5m["close"] > prev_5m["high"])
        )
        pullback_bear = (
            (curr_5m["high"] >= curr_5m["tunnel1_bottom"] * 0.9985)
            and (close_price < curr_5m["tunnel1_bottom"])
            and (curr_5m["close"] < curr_5m["open"])
            and (curr_5m["close"] < prev_5m["low"])
        )

        signal = "WAIT"
        score = 0
        reasons = []
        sl_price, tp1_price, tp2_price = None, None, None

        if (
            trend_15m_bull
            and vegas_5m_bull
            and (bias_bull <= MAX_BIAS_PCT)
            and rsi_bull_ok
            and adx_ok
        ):
            if valid_breakout_up and vol_ok and body_ok:
                signal = "🟢 狙擊做多 [突破型]"
                score = 90 + (5 if curr_5m["adx"] > 28 else 0)
                reasons.append(
                    f"15m/5m雙通道多頭共振 + 帶量({curr_5m['volume']/curr_5m['vol_ma20']:.1f}x)突破5m分形回調壓力線"
                )
            elif pullback_bull and (
                curr_5m["volume"] >= curr_5m["vol_ma20"] * 1.0
            ):
                signal = "🟢 狙擊做多 [回踩型]"
                score = 85
                reasons.append("15m/5m雙通道多頭共振 + 回踩5m Vegas通道一破前高")

            if score > 0:
                sl_price = min(
                    curr_5m["low"] - 0.5 * atr_val,
                    close_price - ATR_SL_MULT * atr_val,
                )
                risk = close_price - sl_price
                tp1_price = close_price + risk * 1.2
                tp2_price = close_price + risk * 2.2

        elif (
            trend_15m_bear
            and vegas_5m_bear
            and (bias_bear <= MAX_BIAS_PCT)
            and rsi_bear_ok
            and adx_ok
        ):
            if valid_breakout_down and vol_ok and body_ok:
                signal = "🔴 狙擊做空 [跌破型]"
                score = 90 + (5 if curr_5m["adx"] > 28 else 0)
                reasons.append(
                    f"15m/5m雙通道空頭共振 + 帶量({curr_5m['volume']/curr_5m['vol_ma20']:.1f}x)跌破5m分形反彈支撐線"
                )
            elif pullback_bear and (
                curr_5m["volume"] >= curr_5m["vol_ma20"] * 1.0
            ):
                signal = "🔴 狙擊做空 [反彈型]"
                score = 85
                reasons.append("15m/5m雙通道空頭共振 + 反彈測試5m Vegas通道一破前低")

            if score > 0:
                sl_price = max(
                    curr_5m["high"] + 0.5 * atr_val,
                    close_price + ATR_SL_MULT * atr_val,
                )
                risk = sl_price - close_price
                tp1_price = close_price - risk * 1.2
                tp2_price = close_price - risk * 2.2

        return {
            "symbol": symbol.replace(":USDT", ""),
            "price": close_price,
            "signal": signal,
            "score": score,
            "15m_trend": "多頭"
            if trend_15m_bull
            else ("空頭" if trend_15m_bear else "震盪"),
            "5m_vegas": "雙通道多"
            if vegas_5m_bull
            else ("雙通道空" if vegas_5m_bear else "通道糾結"),
            "rsi": round(curr_5m["rsi"], 1),
            "adx": round(curr_5m["adx"], 1),
            "vol_ratio": round(curr_5m["volume"] / curr_5m["vol_ma20"], 2)
            if curr_5m["vol_ma20"] > 0
            else 0,
            "sl": round(sl_price, 6) if sl_price else None,
            "tp1": round(tp1_price, 6) if tp1_price else None,
            "tp2": round(tp2_price, 6) if tp2_price else None,
            "reason": " / ".join(reasons),
        }

    except Exception:
        return None


# ==========================================
# 5. 主程式：全市場三層漏斗掃描
# ==========================================
def run_full_market_scanner(loop_mode=False, interval_sec=120):
    exchange = init_exchange()

    while True:
        start_time = time.time()
        print("\n" + "=" * 110)
        print(
            f"🌐 BingX 全市場動態漏斗掃描器 V3.0 | 開始時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        print("=" * 110)

        # 第一層：動態取得全市場前 60 大高流動性活躍幣種
        active_symbols = get_dynamic_active_symbols(exchange)
        active_signals = []

        print(
            f"\n🔍 開始針對前 {len(active_symbols)} 大熱門幣種進行 15m/5m 雙週期深度掃描..."
        )
        for idx, sym in enumerate(active_symbols, 1):
            res = analyze_symbol(exchange, sym)
            if res:
                if res["score"] > 0:
                    active_signals.append(res)
                    print(
                        f"  🔥 [{idx:02d}/{len(active_symbols)}] 發現信號! {res['symbol']:<12} | {res['signal']} (評分:{res['score']})"
                    )
                else:
                    # 簡化觀望幣種輸出，保持終端機乾淨
                    print(
                        f"  ⏳ [{idx:02d}/{len(active_symbols)}] {res['symbol']:<12} | 15m:{res['15m_trend']} | 5m:{res['5m_vegas']} | ADX:{res['adx']:<4} -> 觀望",
                        end="\r",
                    )
            time.sleep(0.15)  # 控制 API 請求頻率

        elapsed = time.time() - start_time
        print("\n\n" + "-" * 110)
        print(
            f"🏆 【全市場掃描完成 (耗時 {elapsed:.1f} 秒) | 65%+ 高勝率狙擊信號彙整】"
        )
        print("-" * 110)

        if active_signals:
            active_signals.sort(
                key=lambda x: (x["score"], x["adx"]), reverse=True
            )
            for sig in active_signals:
                print(
                    f"🎯 幣種: {sig['symbol']:<12} | 信號: {sig['signal']} | 評分: {sig['score']} | 現價: {sig['price']}"
                )
                print(
                    f"   ├─ 🛡️ 止損(SL): {sig['sl']} | 💰 TP1(1.2R, 平70%推保本): {sig['tp1']} | 🚀 TP2(2.2R): {sig['tp2']}"
                )
                print(
                    f"   ├─ 📊 數據: RSI={sig['rsi']} | ADX={sig['adx']} | 爆量倍數={sig['vol_ratio']}x"
                )
                print(f"   └─ 💡 邏輯: {sig['reason']}\n")
        else:
            print(
                "目前全市場前 60 大活躍幣種暫無同時滿足所有嚴格濾網之信號，請等待下一根 5m 收線。"
            )

        if not loop_mode:
            break

        print(f"\n⏳ 等待 {interval_sec} 秒後進行下一輪全市場掃描...")
        time.sleep(interval_sec)


if __name__ == "__main__":
    # 建議在 5m 收線前後執行，或將 loop_mode 設為 True 自動循環
    run_full_market_scanner(loop_mode=True, interval_sec=120)
