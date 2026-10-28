import streamlit as st
import plotly.graph_objects as go
from trading_strategy import TradingStrategyEngine, scan_high_win_rate_markets
import ccxt

st.set_page_config(page_title="BingX 高勝率量化策略雷達", layout="wide")

st.title("🚀 BingX 合約高勝率自動篩選與監控看板")
st.markdown("結合 **Vegas 雙通道發散度** 與 **Auto Trendline (分形)**，自動過濾勝率 **> 65%** 的優質交易機會。")

# 側邊欄控制
st.sidebar.header("⚙️ 篩選與設定面板")
scanner_timeframe = st.sidebar.selectbox("掃描與分析 K線週期", ["15m", "1h", "4h", "1d"], index=1)
target_win_rate = st.sidebar.slider("最低勝率過濾門檻 (%)", min_value=60, max_value=80, value=65, step=1)

# 觸發自動掃描按鈕
st.sidebar.markdown("---")
run_scanner = st.sidebar.button("🔍 開始掃描全市場高勝率幣種")

# 動態取得所有幣種作為備用手動下拉
@st.cache_data(ttl=3600)
def get_all_symbols():
    try:
        ex = ccxt.bingx({'enableRateLimit': True})
        ex.load_markets()
        return sorted([s for s in ex.symbols if ':USDT' in s])
    except:
        return ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]

all_symbols = get_all_symbols()

# 主頁面邏輯：如果點擊了自動掃描
if run_scanner or 'scanned_results' not in st.session_state:
    with st.spinner(f'正在高效率掃描 BingX 市場，尋找勝率大於 {target_win_rate}% 的共振機會...'):
        st.session_state['scanned_results'] = scan_high_win_rate_markets(timeframe=scanner_timeframe, min_win_rate=float(target_win_rate))

qualified_coins = st.session_state['scanned_results']

st.subheader(f"🎯 符合勝率 > {target_win_rate}% 條件的精選幣種清單 (共 {len(qualified_coins)} 個)")

if qualified_coins:
    # 製作清單選單供使用者快速切換檢視
    coin_options = [item['symbol'] for item in qualified_coins]
    selected_symbol = st.selectbox("👇 選擇你想詳細檢視的精選幣種：", coin_options)
    
    # 找出對應的資料
    analysis = next((item for item in qualified_coins if item['symbol'] == selected_symbol), None)
    
    if analysis:
        # 顯示核心指標數據
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("幣種與價格", f"{analysis['symbol']}", f"${analysis['close']:,.2f}")
        col2.metric("Vegas 趨勢狀態", analysis['trend'])
        col3.metric("系統預估勝率", f"{analysis['win_rate']}% 🌟")
        col4.metric("建議策略訊號", analysis['signal'])

        st.markdown("---")
        
        # 顯示風控點位
        st.subheader("🎯 該幣種精準執行點位 (Risk & Reward)")
        r_col1, r_col2, r_col3 = st.columns(3)
        r_col1.error(f"🛑 建議止損價 (Stop Loss): ${analysis['sl']:,.2f}")
        r_col2.success(f"🟢 第一目標止盈 (TP1): ${analysis['tp1']:,.2f}")
        r_col3.success(f"🎯 第二目標止盈 (TP2): ${analysis['tp2']:,.2f}")

        # 繪製 Plotly 互動圖表
        st.markdown("---")
        st.subheader(f"📈 {analysis['symbol']} - Vegas 隧道互動走勢圖")
        
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
    st.warning(f"目前市場在 {scanner_timeframe} 週期下沒有符合勝率 > {target_win_rate}% 的強勢發散幣種（可能多數在盤整）。建議降低門檻或切換至 15m / 1h 週期重新掃描！")
