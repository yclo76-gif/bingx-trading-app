import streamlit as st
import plotly.graph_objects as go
from trading_strategy import quick_scan_watchlist, TradingStrategyEngine

st.set_page_config(page_title="極短線高勝率雷達看板", layout="wide")

st.title("⚡ BingX 5m / 15m 極短線高勝率策略雷達")
st.markdown("自動掃描自選清單，過濾出 **勝率 $\ge 65\%$** 的強勢發散幣種，點選左側選單可瞬間切換右側圖表與明細。")

# 側邊欄設定
st.sidebar.header("⚙️ 極短線掃描設定")

selected_timeframe = st.sidebar.selectbox("選擇短線 K線週期", ["5m", "15m"], index=1)
min_win_rate_target = st.sidebar.slider("勝率過濾門檻 (%)", min_value=60, max_value=75, value=65, step=1)

# 加入清除快取按鈕，讓想強制重新整理的人使用
if st.sidebar.button("🔄 強制重新整理掃描結果"):
    st.cache_data.clear()
    st.rerun()

# 關鍵優化 1：使用 @st.cache_data 快取整體掃描清單，避免切換時重複掃描
@st.cache_data(ttl=120)
def get_cached_qualified_coins(timeframe, min_wr):
    return quick_scan_watchlist(timeframe=timeframe, min_win_rate=float(min_wr))

with st.spinner(f'正在以 {selected_timeframe} 週期快速檢索自選清單...'):
    qualified_coins = get_cached_qualified_coins(selected_timeframe, min_win_rate_target)

st.sidebar.markdown("---")
st.sidebar.subheader(f"🎯 符合條件幣種 ({len(qualified_coins)} 個)")

if qualified_coins:
    coin_symbols = [item['symbol'] for item in qualified_coins]
    
    # 讓左側選單記憶狀態
    selected_symbol = st.sidebar.radio("👇 點選查看右側詳情：", coin_symbols, key="selected_coin_radio")
    
    # 關鍵優化 2：針對單一幣種加入獨立快取，實現點擊左側時秒開、不反灰
    @st.cache_data(ttl=30)
    def get_single_coin_analysis(symbol, timeframe):
        engine = TradingStrategyEngine(symbol=symbol, timeframe=timeframe)
        return engine.analyze_market()

    with st.spinner(f'正在載入 {selected_symbol} 盤面數據...'):
        analysis = get_single_coin_analysis(selected_symbol, selected_timeframe)
    
    if analysis:
        # 右側主窗格呈現
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("當前選定幣種", analysis['symbol'], f"${analysis['close']:,.2f}")
        col2.metric("Vegas 短線趨勢", analysis['trend'])
        col3.metric("策略預估勝率", f"{analysis['win_rate']}% 🌟")
        col4.metric("建議短線訊號", analysis['signal'])

        st.markdown("---")
        
        # 顯示短線風控點位
        st.subheader("🎯 短線精準執行點位 (Risk & Reward)")
        r_col1, r_col2, r_col3 = st.columns(3)
        r_col1.error(f"🛑 建議止損價 (Stop Loss): ${analysis['sl']:,.2f}")
        r_col2.success(f"🟢 第一目標止盈 (TP1): ${analysis['tp1']:,.2f}")
        r_col3.success(f"🎯 第二目標止盈 (TP2): ${analysis['tp2']:,.2f}")

        # 繪製右側主圖表
        st.markdown("---")
        st.subheader(f"📈 {analysis['symbol']} ({selected_timeframe}) - Vegas 隧道走勢圖")
        
        df = analysis['dataframe']
        fig = go.Figure()

        fig.add_trace(go.Candlestick(
            x=df['timestamp'],
            open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            name='K線'
        ))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_144'], line=dict(color='blue', width=1), name='EMA 144'))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_169'], line=dict(color='blue', width=1), name='EMA 169'))
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
    st.warning(f"在 {selected_timeframe} 週期下，目前自選清單中沒有符合勝率 $\ge {min_win_rate_target}\%$ 的強勢發散標的。")
