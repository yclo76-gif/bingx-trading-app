import streamlit as st
import plotly.graph_objects as go
from trading_strategy import TradingStrategyEngine

st.set_page_config(page_title="BingX 量化策略監控看板", layout="wide")

st.title("🚀 BingX 合約交易決策與止盈止損監控看板")
st.markdown("結合 **Vegas 雙通道** 與 **Auto Trendline (分形)** 的高勝率自動化策略系統。")

# 側邊欄設定
st.sidebar.header("⚙️ 交易參數設定")
symbol_option = st.sidebar.selectbox("選擇交易幣種 (USDT永續)", ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT"])
timeframe_option = st.sidebar.selectbox("選擇K線週期", ["15m", "1h", "4h", "1d"], index=1)

# 初始化引擎並抓取數據
engine = TradingStrategyEngine(symbol=symbol_option, timeframe=timeframe_option)

if st.button("🔄 立即重新整理盤面分析"):
    st.rerun()

with st.spinner('正在連線 BingX 計算指標中...'):
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