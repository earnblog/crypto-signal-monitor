import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time

st.set_page_config(
    page_title="加密信号监控",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.stApp { background: #0d0f14; color: #e0e0e0; }
[data-testid="stSidebar"] { background: #0a0c10 !important; border-right: 1px solid #1e2230; }
h1, h2, h3 { color: #e0e0e0 !important; }
.metric-card {
    background: #13161e; border: 1px solid #1e2230;
    border-radius: 10px; padding: 14px 16px; margin-bottom: 8px;
}
.metric-label { font-size: 12px; color: #888; margin-bottom: 4px; }
.metric-value { font-size: 22px; font-weight: 600; }
.signal-bull { color: #4CAF50; }
.signal-warn { color: #FF9800; }
.signal-bear { color: #f44336; }
.verdict-box {
    border-radius: 10px; padding: 16px 18px; margin-top: 12px;
    font-size: 14px; line-height: 1.7;
}
.verdict-bull { background: #0d2018; border: 1px solid #4CAF50; color: #a5d6a7; }
.verdict-warn { background: #1e1600; border: 1px solid #FF9800; color: #ffcc80; }
.verdict-bear { background: #1e0a0a; border: 1px solid #f44336; color: #ef9a9a; }
.tag {
    display: inline-block; font-size: 11px; padding: 2px 8px;
    border-radius: 5px; margin-left: 6px; vertical-align: middle;
}
.tag-bull { background: #0d2018; color: #4CAF50; border: 1px solid #4CAF50; }
.tag-warn { background: #1e1600; color: #FF9800; border: 1px solid #FF9800; }
.tag-bear { background: #1e0a0a; color: #f44336; border: 1px solid #f44336; }
.divider { border-top: 1px solid #1e2230; margin: 10px 0; }
.update-time { font-size: 11px; color: #555; margin-top: 8px; }
</style>
""", unsafe_allow_html=True)

OKX_BASE = "https://www.okx.com/api/v5"
FG_URL = "https://api.alternative.me/fng/?limit=1"
CG_BASE = "https://api.coingecko.com/api/v3"

COIN_MAP = {
    "BTC-USDT": "bitcoin",
    "ETH-USDT": "ethereum",
    "SOL-USDT": "solana",
    "BNB-USDT": "binancecoin",
    "XRP-USDT": "ripple",
    "DOGE-USDT": "dogecoin",
    "ADA-USDT": "cardano",
    "AVAX-USDT": "avalanche-2",
    "MATIC-USDT": "matic-network",
    "LINK-USDT": "chainlink",
}

@st.cache_data(ttl=60)
def get_ticker(inst_id):
    try:
        r = requests.get(f"{OKX_BASE}/market/ticker?instId={inst_id}", timeout=8)
        d = r.json()
        if d.get("code") == "0":
            return d["data"][0]
    except:
        pass
    return None

@st.cache_data(ttl=60)
def get_candles(inst_id, bar="1D", limit=7):
    try:
        r = requests.get(f"{OKX_BASE}/market/candles?instId={inst_id}&bar={bar}&limit={limit}", timeout=8)
        d = r.json()
        if d.get("code") == "0":
            return d["data"]
    except:
        pass
    return []

@st.cache_data(ttl=60)
def get_swap_ticker(inst_id):
    swap_id = inst_id.replace("-USDT", "-USDT-SWAP")
    try:
        r = requests.get(f"{OKX_BASE}/market/ticker?instId={swap_id}", timeout=8)
        d = r.json()
        if d.get("code") == "0":
            return d["data"][0]
    except:
        pass
    return None

@st.cache_data(ttl=300)
def get_cg_data(coin_id):
    """返回 (market_cap, total_24h_volume_usd) 全市场数据"""
    try:
        r = requests.get(
            f"{CG_BASE}/simple/price?ids={coin_id}&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true",
            timeout=8
        )
        d = r.json()
        if coin_id in d:
            mc = d[coin_id].get("usd_market_cap", 0)
            vol = d[coin_id].get("usd_24h_vol", 0)
            return mc, vol
    except:
        pass
    return 0, 0

@st.cache_data(ttl=300)
def get_fear_greed():
    try:
        r = requests.get(FG_URL, timeout=8)
        d = r.json()
        if "data" in d and len(d["data"]) > 0:
            val = int(d["data"][0]["value"])
            label = d["data"][0]["value_classification"]
            return val, label
    except:
        pass
    return None, None

def calc_vol_ratio(candles):
    if len(candles) < 6:
        return None
    vols = [float(c[5]) for c in candles]
    today_vol = vols[0]
    avg5 = np.mean(vols[1:6])
    if avg5 == 0:
        return None
    return today_vol / avg5

def score_vol_ratio(v):
    if v is None: return 40, "warn", "数据不足"
    if v >= 2.5: return 85, "bull", f"强放量 {v:.2f}x"
    if v >= 1.5: return 70, "bull", f"放量 {v:.2f}x"
    if v >= 1.0: return 55, "warn", f"正常 {v:.2f}x"
    if v >= 0.7: return 40, "warn", f"缩量 {v:.2f}x"
    return 25, "bear", f"明显缩量 {v:.2f}x"

def score_turnover(turnover_pct, inst_id):
    is_major = any(x in inst_id for x in ["BTC", "ETH", "BNB"])
    if turnover_pct <= 0: return 40, "warn", "数据不足"
    if is_major:
        if turnover_pct >= 0.5: return 80, "bull", f"{turnover_pct:.2f}% 活跃"
        if turnover_pct >= 0.15: return 60, "bull", f"{turnover_pct:.2f}% 正常"
        return 35, "warn", f"{turnover_pct:.2f}% 偏低"
    else:
        if turnover_pct >= 5: return 80, "bull", f"{turnover_pct:.2f}% 活跃"
        if turnover_pct >= 1.5: return 60, "bull", f"{turnover_pct:.2f}% 正常"
        return 35, "warn", f"{turnover_pct:.2f}% 偏低"

def score_fund_auth(spot_vol_usd, swap_vol_usd):
    if spot_vol_usd <= 0 or swap_vol_usd <= 0:
        return 40, "warn", "数据不足"
    total = spot_vol_usd + swap_vol_usd
    ratio = spot_vol_usd / total
    if ratio >= 0.4: return 75, "bull", f"现货占 {ratio*100:.0f}%，买盘真实"
    if ratio >= 0.2: return 55, "warn", f"现货占 {ratio*100:.0f}%，合约偏多"
    return 25, "bear", f"现货仅 {ratio*100:.0f}%，合约主导"

def score_fg(fg_val):
    if fg_val is None: return 45, "warn", "数据不足"
    if fg_val >= 80: return 25, "bear", f"{fg_val} 极度贪婪，注意回调"
    if fg_val >= 60: return 45, "warn", f"{fg_val} 贪婪，谨慎"
    if fg_val >= 40: return 65, "bull", f"{fg_val} 中性，偏健康"
    if fg_val >= 20: return 70, "bull", f"{fg_val} 恐惧，逆向买点"
    return 55, "warn", f"{fg_val} 极度恐惧，观望"

def score_ex_flow(vol_ratio, spot_ratio):
    # 用量比 + 现货占比联合估算交易所流向
    if vol_ratio is None: return 45, "warn", "综合观察中"
    if vol_ratio >= 1.5 and spot_ratio >= 0.3:
        return 70, "bull", "量价配合，资金流入信号"
    if vol_ratio < 0.8 and spot_ratio < 0.2:
        return 30, "bear", "缩量+合约主导，资金流出信号"
    return 50, "warn", "信号混合，暂无明确方向"

def weighted_score(scores):
    weights = [0.25, 0.20, 0.20, 0.20, 0.15]
    return int(sum(s * w for s, w in zip(scores, weights)))

def make_radar_fig(scores, labels):
    vals = scores + [scores[0]]
    lbls = labels + [labels[0]]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=vals, theta=lbls,
        fill='toself',
        fillcolor='rgba(29,158,117,0.12)',
        line=dict(color='#1D9E75', width=2),
        marker=dict(color='#1D9E75', size=5),
    ))
    fig.update_layout(
        polar=dict(
            bgcolor='#13161e',
            radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=10, color='#555'), gridcolor='#1e2230'),
            angularaxis=dict(tickfont=dict(size=11, color='#aaa'), gridcolor='#1e2230', linecolor='#1e2230'),
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=40, r=40, t=20, b=20),
        height=280,
        showlegend=False,
    )
    return fig

def make_kline_fig(candles, inst_id):
    if not candles:
        return None
    df = pd.DataFrame(candles, columns=["ts","o","h","l","c","vol","volCcy","volCcyQuote","confirm"])
    df = df.iloc[::-1].reset_index(drop=True)
    for col in ["o","h","l","c","vol"]:
        df[col] = df[col].astype(float)
    df["date"] = pd.to_datetime(df["ts"].astype(int), unit='ms')

    colors = ['#4CAF50' if c >= o else '#f44336' for o, c in zip(df["o"], df["c"])]

    fig = go.Figure(data=[go.Candlestick(
        x=df["date"], open=df["o"], high=df["h"], low=df["l"], close=df["c"],
        increasing_line_color='#4CAF50', decreasing_line_color='#f44336',
        increasing_fillcolor='#4CAF50', decreasing_fillcolor='#f44336',
        name=inst_id,
    )])
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#13161e',
        xaxis=dict(gridcolor='#1e2230', color='#888', showgrid=False),
        yaxis=dict(gridcolor='#1e2230', color='#888'),
        margin=dict(l=10, r=10, t=10, b=10),
        height=200,
        xaxis_rangeslider_visible=False,
    )
    return fig

# ─── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📡 信号监控")
    st.markdown("---")

    inst_options = list(COIN_MAP.keys()) + ["自定义"]
    inst_choice = st.selectbox("选择币种", inst_options, index=0)

    if inst_choice == "自定义":
        inst_id = st.text_input("输入币种（如 PEPE-USDT）", "PEPE-USDT").upper()
        coin_id = None
    else:
        inst_id = inst_choice
        coin_id = COIN_MAP.get(inst_id)

    auto_refresh = st.toggle("自动刷新（60秒）", value=False)
    if st.button("🔄 立即刷新", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("""
    **评分说明**
    - 🟢 65+ 看多
    - 🟡 45-64 观望
    - 🔴 <45 看空

    **数据来源**
    - OKX 公开 API
    - CoinGecko（市值）
    - alternative.me（恐惧贪婪）

    *仅供参考，非投资建议*
    """)

# ─── Main ──────────────────────────────────────────────────────────────────────

st.markdown(f"## 📡 {inst_id} 信号仪表盘")

with st.spinner("拉取数据中..."):
    ticker = get_ticker(inst_id)
    candles_1d = get_candles(inst_id, bar="1D", limit=7)
    candles_4h = get_candles(inst_id, bar="4H", limit=50)
    swap_ticker = get_swap_ticker(inst_id)
    fg_val, fg_label = get_fear_greed()
    cg_market_cap, cg_vol_24h = get_cg_data(coin_id) if coin_id else (0, 0)

if not ticker:
    st.error(f"无法获取 {inst_id} 数据，请检查币种名称是否正确（如 BTC-USDT）")
    st.stop()

# ── 基础数据计算 ────────────────────────────────────────────────────────────────

last_price = float(ticker.get("last", 0))
open_24h = float(ticker.get("open24h", last_price))
vol_24h = float(ticker.get("vol24h", 0))           # 币本位成交量
# OKX volCcy24h = 计价货币成交额（USDT），直接就是成交额
vol_ccy_24h = float(ticker.get("volCcy24h", 0))
# 如果 volCcy24h 异常小，用 vol24h * price 估算
if vol_ccy_24h < vol_24h * last_price * 0.01 and vol_24h > 0 and last_price > 0:
    vol_ccy_24h = vol_24h * last_price
change_24h = ((last_price - open_24h) / open_24h * 100) if open_24h > 0 else 0

# 合约成交额：OKX swap volCcy24h 是张数成交额，需转换
# swap vol24h = 张数，每张 = 0.01 BTC（BTC合约），volCcy24h = USDT成交额
swap_vol_usd = 0.0
if swap_ticker:
    # volCcy24h on BTC-USDT-SWAP = BTC成交量，需乘以价格换算成USDT
    swap_vol_ccy = float(swap_ticker.get("volCcy24h", 0))
    swap_vol_usd = swap_vol_ccy * last_price
spot_vol_usd = vol_ccy_24h
total_vol = spot_vol_usd + swap_vol_usd
spot_ratio = spot_vol_usd / total_vol if total_vol > 0 else 0

# 换手率用 CoinGecko 全市场成交量，更准确
market_cap = cg_market_cap
global_vol_24h = cg_vol_24h if cg_vol_24h > 0 else vol_ccy_24h
turnover_pct = (global_vol_24h / market_cap * 100) if market_cap > 0 else 0
vol_ratio = calc_vol_ratio(candles_1d)

# ── 评分 ────────────────────────────────────────────────────────────────────────

s1, c1, d1 = score_vol_ratio(vol_ratio)
s2, c2, d2 = score_turnover(turnover_pct, inst_id)
s3, c3, d3 = score_fund_auth(spot_vol_usd, swap_vol_usd)
s4, c4, d4 = score_ex_flow(vol_ratio, spot_ratio)
s5, c5, d5 = score_fg(fg_val)
total = weighted_score([s1, s2, s3, s4, s5])

# ── Top metrics ─────────────────────────────────────────────────────────────────


def metric_card(col, label, value, sub="", color=None):
    color_style = f"color:{color};" if color else ""
    col.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value" style="{color_style}">{value}</div>
        <div style="font-size:11px;color:#555;margin-top:3px">{sub}</div>
    </div>""", unsafe_allow_html=True)

price_color = "#4CAF50" if change_24h >= 0 else "#f44336"
change_str = f"{'+' if change_24h>=0 else ''}{change_24h:.2f}%"
total_color = "#4CAF50" if total >= 65 else "#FF9800" if total >= 45 else "#f44336"
total_label = "看多" if total >= 65 else "观望" if total >= 45 else "看空"

swap_price = float(swap_ticker.get("last", 0)) if swap_ticker else 0
col1, col2, col3, col4, col5 = st.columns(5)
price_str = f"${last_price:,.0f}" if last_price >= 1 else f"${last_price:.6f}"
swap_str = f"合约 ${swap_price:,.0f}" if swap_price > 0 else "合约 N/A"
metric_card(col1, "现货价格", price_str, swap_str, price_color)
vol_display = global_vol_24h if global_vol_24h > 0 else vol_ccy_24h
metric_card(col2, "全市场24h成交额", f"${vol_display/1e9:.2f}B" if vol_display >= 1e9 else f"${vol_display/1e6:.0f}M", "CoinGecko 全市场")
metric_card(col3, "换手率", f"{turnover_pct:.2f}%" if turnover_pct > 0 else "N/A", "成交额/市值")
metric_card(col4, "恐慌贪婪", str(fg_val) if fg_val else "—", fg_label or "")
metric_card(col5, "综合评分", f"{total}/100", total_label, total_color)

# ── Main content ────────────────────────────────────────────────────────────────

left_col, right_col = st.columns([1.1, 0.9])

with left_col:
    st.markdown("##### 五维度信号")

    SIGNAL_TIPS = {
        "量比": "今日成交量 ÷ 近5日日均成交量。>1.5 放量，<0.8 缩量。放量上涨是强势信号，缩量上涨需警惕。",
        "换手率": "全市场24h成交额 ÷ 流通市值。BTC正常2-4%，山寨币正常5-15%。过高可能是炒作，过低说明没人关注。",
        "资金真实性": "OKX现货成交量占（现货+合约）总量的比例。现货占比高说明真实买盘驱动；合约占比高说明是杠杆/投机推动，价格可靠性低。",
        "交易所流向": "综合量比和现货占比估算。成交量放大且现货主导 = 资金流入信号；缩量且合约主导 = 资金流出信号。",
        "恐慌贪婪": "0-100的市场情绪指数（alternative.me）。<25极度恐惧（逆向看多机会），>75极度贪婪（注意回调风险），40-60中性健康。",
    }
    signals = [
        ("量比", d1, c1, f"{vol_ratio:.2f}x" if vol_ratio else "—"),
        ("换手率", d2, c2, f"{turnover_pct:.2f}%" if turnover_pct > 0 else "N/A"),
        ("资金真实性", d3, c3, f"现货 {spot_ratio*100:.0f}%"),
        ("交易所流向", d4, c4, "综合估算"),
        ("恐慌贪婪", d5, c5, f"{fg_val} · {fg_label}" if fg_val else "—"),
    ]

    color_map = {"bull": "#4CAF50", "warn": "#FF9800", "bear": "#f44336"}
    tag_cls = {"bull": "tag-bull", "warn": "tag-warn", "bear": "tag-bear"}
    tag_txt = {"bull": "看多", "warn": "中性", "bear": "看空"}

    for name, desc, cls, val in signals:
        dot_color = color_map[cls]
        tip = SIGNAL_TIPS.get(name, "")
        st.markdown(f"""
        <div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid #1e2230">
            <div style="width:8px;height:8px;border-radius:50%;background:{dot_color};flex-shrink:0;margin-top:5px"></div>
            <div style="flex:1">
                <span style="font-size:13px;color:#aaa">{name}</span>
                <div style="font-size:11px;color:#555;margin-top:2px">{desc}</div>
                <div style="font-size:11px;color:#3a4a5a;margin-top:3px;line-height:1.5">{tip}</div>
            </div>
            <div style="text-align:right;flex-shrink:0;margin-left:8px">
                <div style="font-size:13px;font-weight:500;color:#ddd">{val}</div>
                <span class="tag {tag_cls[cls]}">{tag_txt[cls]}</span>
            </div>
        </div>""", unsafe_allow_html=True)

    # K线小图
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    st.markdown("##### 近期K线（日线）")
    kline_fig = make_kline_fig(candles_1d, inst_id)
    if kline_fig:
        st.plotly_chart(kline_fig, use_container_width=True, config={"displayModeBar": False})

with right_col:
    st.markdown("##### 雷达图")
    radar_scores = [s1, s2, s3, s4, s5]
    radar_labels = ["量比", "换手率", "资金真实性", "交易所流向", "恐慌贪婪"]
    radar_fig = make_radar_fig(radar_scores, radar_labels)
    st.plotly_chart(radar_fig, use_container_width=True, config={"displayModeBar": False})

    # 详细数据
    st.markdown("##### 原始数据")
    raw_data = {
        "指标": ["全市场24h成交额(CG)", "OKX现货成交额", "OKX合约成交额", "市值", "量比"],
        "数值": [
            f"${global_vol_24h/1e9:.2f}B" if global_vol_24h >= 1e9 else f"${global_vol_24h/1e6:.0f}M",
            f"${spot_vol_usd/1e9:.3f}B" if spot_vol_usd >= 1e9 else f"${spot_vol_usd/1e6:.1f}M（OKX）",
            f"${swap_vol_usd/1e9:.3f}B" if swap_vol_usd >= 1e9 else f"${swap_vol_usd/1e6:.1f}M（OKX）",
            f"${market_cap/1e9:.1f}B" if market_cap >= 1e9 else ("N/A" if market_cap == 0 else f"${market_cap/1e6:.0f}M"),
            f"{vol_ratio:.2f}x" if vol_ratio else "—",
        ]
    }
    df_raw = pd.DataFrame(raw_data)
    st.dataframe(df_raw, hide_index=True, use_container_width=True)

# ── Verdict ──────────────────────────────────────────────────────────────────

if total >= 65:
    verdict_cls = "verdict-bull"
    verdict_title = f"🟢 看多 · 综合评分 {total}/100"
    pos_sigs = [s[0] for s in signals if s[2] == "bull"]
    neg_sigs = [s[0] for s in signals if s[2] == "bear"]
    verdict_body = f"多项信号偏多：{', '.join(pos_sigs)}。"
    if neg_sigs:
        verdict_body += f" 注意：{', '.join(neg_sigs)} 信号偏空，注意风险控制。"
    verdict_body += " 短线可关注做多机会，严格设置止损。"
elif total >= 45:
    verdict_cls = "verdict-warn"
    verdict_title = f"🟡 观望 · 综合评分 {total}/100"
    bull_sigs = [s[0] for s in signals if s[2] == "bull"]
    bear_sigs = [s[0] for s in signals if s[2] == "bear"]
    verdict_body = f"信号分化，暂无明确方向。"
    if bull_sigs:
        verdict_body += f" 利多：{', '.join(bull_sigs)}。"
    if bear_sigs:
        verdict_body += f" 利空：{', '.join(bear_sigs)}。"
    verdict_body += " 建议等待信号更清晰后再入场。"
else:
    verdict_cls = "verdict-bear"
    verdict_title = f"🔴 看空 · 综合评分 {total}/100"
    neg_sigs = [s[0] for s in signals if s[2] == "bear"]
    verdict_body = f"多项指标偏空：{', '.join(neg_sigs)}。建议控制仓位，等待信号改善。"

st.markdown(f"""
<div class="verdict-box {verdict_cls}">
    <div style="font-size:15px;font-weight:600;margin-bottom:6px">{verdict_title}</div>
    <div>{verdict_body}</div>
</div>""", unsafe_allow_html=True)

# ── 指标说明 ─────────────────────────────────────────────────────────────────

with st.expander("📖 指标说明 & 评分逻辑", expanded=False):
    st.markdown("""
**价格说明**
- **现货价**：OKX 现货市场实时成交价（BTC-USDT）
- **合约价**：OKX 永续合约价（BTC-USDT-SWAP），与现货有基差，通常差 $10-50，正常现象

---

**五维度指标说明**

| 指标 | 含义 | 看多信号 | 看空信号 |
|------|------|----------|----------|
| **量比** | 今日成交量 ÷ 近5日均量 | >1.5（放量） | <0.8（缩量） |
| **换手率** | 全市场24h成交额 ÷ 市值 | BTC>2%，山寨>5% | 极低说明无人关注 |
| **资金真实性** | OKX现货占（现货+合约）比例 | 现货>40%，真实买盘 | 现货<20%，合约主导 |
| **交易所流向** | 量比+现货占比联合估算 | 放量+现货主导 | 缩量+合约主导 |
| **恐慌贪婪** | 市场情绪指数 0-100 | 25-55 健康/恐惧区 | >75 极度贪婪 |

---

**综合评分权重**

量比 25% · 换手率 20% · 资金真实性 20% · 交易所流向 20% · 恐慌贪婪 15%

- 🟢 **65分以上**：多数信号偏多，可关注做多机会
- 🟡 **45-64分**：信号分化，建议观望等待方向
- 🔴 **45分以下**：多数信号偏空，建议控制仓位

---

**数据来源说明**
- 价格 / 量比 / 现货合约成交量：OKX 公开 API（实时）
- 全市场成交额 / 市值：CoinGecko（5分钟缓存）
- 恐慌贪婪指数：alternative.me（每日更新）
- 交易所流向：由量比和现货占比推算，非链上真实数据

> 所有数据仅供参考，不构成投资建议。短线交易风险极高，请做好风险管理。
""")

# ── Footer ───────────────────────────────────────────────────────────────────

st.markdown(f"""
<div class="update-time">
    最后更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ·
    数据来源：OKX 公开 API · CoinGecko · alternative.me ·
    仅供参考，不构成投资建议
</div>""", unsafe_allow_html=True)

if auto_refresh:
    time.sleep(60)
    st.rerun()
