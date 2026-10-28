import streamlit as st
import plotly.graph_objects as go
from trading_strategy import TradingStrategyEngine
import ccxt

st.set_page_config(page_title="BingX 量化策略監控看板", layout="wide")

st.title("🚀 BingX 合約交易決策與止盈止損監控看板")
st.markdown("結合 **Vegas 雙通道** 與 **Auto Trendline (分形)** 的高勝率自動化策略系統。")

# 動態從 BingX 抓取所有可用的 USDT 永續合約幣種
@st.cache_data(ttl=3600)
def get_bingx_symbols():
    try:
        exchange = ccxt.bingx({'enableRateLimit': True})
        exchange.load_markets()
        # 篩選出帶有 :USDT 的永續合約
        symbols = [symbol for symbol in exchange.symbols if ':USDT' in symbol]
        return sorted(symbols) if symbols else ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
    except Exception:
        # 若連線失敗的備用清單
        return ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT", "DOGE/USDT:USDT"]

all_symbols = get_bingx_symbols()

# 側邊欄設定
st.sidebar.header("⚙️ 交易參數設定")

# 支援搜尋或下拉選擇全部幣種
symbol_option = st.sidebar.selectbox("選擇交易幣種 (USDT永續)", all_symbols, index=all_symbols.index("ETH/USDT:USDT") if "ETH/USDT:USDT" in all_symbols else 0)

# 解鎖更完整的時區選擇（包含 1m, 5m 超短線）
timeframe_option = st.sidebar.selectbox("選擇K線週期", ["1m", "5m", "15m", "1h", "4h", "1d"], index=2)

# 初始化引擎並抓取數據
engine = TradingStrategyEngine(symbol=symbol_option, timeframe=timeframe_option)

if st.button("🔄 立即重新整理盤面分析"):
    st.rerun()

with st.spinner(f'正在連線 BingX 抓取 {symbol_option} ({timeframe_option}) 數據中...'):
    analysis = engine.analyze_market()

if analysis:
    # 顯示核心指標數據
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("當前幣種價格", f"${analysis['close']:,.2f}")
    col2.metric("Vegas 大趨勢判斷", analysis['trend'])
    col3.metric("當前策略訊號", analysis['signal'])
    col4.metric("建議進場點位", f"${analysis['entry']:,.2f}")

    st.markdown("---")
    
    # 顯示風控點位 (止盈止損)
    st.subheader("🎯 建議執行點位 (Risk & Reward)")
    r_col1, r_col2, r_col3 = st.columns(3)
    r_col1.error(f"🛑 建議止損價 (Stop Loss): ${analysis['sl']:,.2f}")
    r_col2.success(f"🟢 第一目標止盈 (TP1): ${analysis['tp1']:,.2f}")
    r_col3.success(f"🎯 第二目標止盈 (TP2): ${analysis['tp2']:,.2f}")

    # 繪製 Plotly 互動圖表
    st.markdown("---")
    st.subheader("📈 Vegas 隧道與價格互動圖表")
    
    df = analysis['dataframe']
    fig = go.Figure()

    # K線圖
    fig.add_trace(go.Candlestick(
        x=df['timestamp'],
        open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name='K線'
    ))

    # Vegas 隧道快線
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_144'], line=dict(color='blue', width=1), name='EMA 144'))
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_169'], line=dict(color='blue', width=1), name='EMA 169'))
    
    # Vegas 隧道慢線
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_576'], line=dict(color='red', width=1), name='EMA 576'))
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_676'], line=dict(color='red', width=1), name='EMA 676'))

    fig.update_layout(
        xaxis_title='時間',
        yaxis_title='價格 (USDT)',
        height=600,
        template='plotly_dark'
    )
    
    st.plotly_chart(fig, use_container_width=True)
else:
    st.error("無法取得市場數據，請檢查網路連線或稍後再試。")
