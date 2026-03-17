from pathlib import Path
import streamlit as st

from src.data_loader import get_clean_data_bundle
from src.filters import apply_global_filters, render_global_sidebar
from src.metrics import get_kpi_snapshot
from src.styles import apply_global_styles
from src.tables import render_detail_table
from src.utils import format_count, format_date, format_money, setup_page


setup_page("供应链降本分析")
apply_global_styles()

st.markdown("<div class='page-title'>供应链降本分析</div>", unsafe_allow_html=True)
st.markdown("<div class='page-subtitle'>供应链降本分析看板，左侧切片器可进行全局筛选。</div>", unsafe_allow_html=True)

bundle = get_clean_data_bundle()
render_global_sidebar(bundle)

if bundle.error:
    st.error(bundle.error)
    st.stop()

fact_df = bundle.fact_df.copy()
filtered_df = apply_global_filters(fact_df, st.session_state.global_filters)
summary = get_kpi_snapshot(filtered_df, fact_df)

card_cols = st.columns(4)
with card_cols[0]:
    st.markdown(
        f"""
        <div class='hero-card'>
            <div class='hero-label'>最新日期</div>
            <div class='hero-value'>{format_date(summary.cutoff_date)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with card_cols[1]:
    st.markdown(
        f"""
        <div class='hero-card'>
            <div class='hero-label'>总入库金额</div>
            <div class='hero-value'>{format_money(summary.total_receipt_amount)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with card_cols[2]:
    st.markdown(
        f"""
        <div class='hero-card'>
            <div class='hero-label'>供应商数量</div>
            <div class='hero-value'>{format_count(summary.supplier_count)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with card_cols[3]:
    st.markdown(
        f"""
        <div class='hero-card'>
            <div class='hero-label'>物料编码数</div>
            <div class='hero-value'>{format_count(summary.material_count)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("### 项目说明")
st.markdown(
    """
- 左侧筛选器为全局筛选，切换页面后会持续保留。
- 页面图表支持点击联动，下方表格或矩阵会根据点击结果进一步过滤。
- 如飞书读取失败，页面会展示明确错误信息，可在左侧点击 `刷新数据` 清空缓存后重试。
- 主页提供快速概览，完整分析页面请从左侧 Pages 导航进入。
    """
)

st.markdown("### 当前筛选结果预览")
render_detail_table(
    filtered_df,
    key="home_preview_table",
    height=360,
    max_rows=200,
)
