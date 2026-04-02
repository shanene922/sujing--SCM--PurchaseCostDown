from __future__ import annotations

import streamlit as st

from src.charts import (
    create_category_combo_chart,
    create_category_metric_bar,
    create_category_status_donut,
    create_subcategory_top_chart,
    render_clickable_chart,
)
from src.data_loader import get_clean_data_bundle
from src.filters import apply_chart_selections, apply_global_filters, render_global_sidebar
from src.metrics import total_costdown_amount_negative, total_receipt_amount
from src.state import get_page_chart_selections
from src.styles import apply_global_styles
from src.tables import render_matrix_table
from src.utils import format_count, format_money, format_percent, safe_divide, setup_page


setup_page("品类降本情况一览")
apply_global_styles()

st.markdown("<div class='page-title'>品类降本情况一览</div>", unsafe_allow_html=True)
st.markdown("<div class='page-subtitle'>从一级、二级到三级品类查看降本贡献、入库规模与月度结构变化。</div>", unsafe_allow_html=True)

bundle = get_clean_data_bundle()
render_global_sidebar(bundle)
if bundle.error:
    st.error(bundle.error)
    st.stop()

filtered_df = apply_global_filters(bundle.fact_df, st.session_state.global_filters)


def _count_unique(df, col: str) -> int:
    return int(df[col].dropna().nunique()) if col in df.columns else 0


def render_metric_card(label: str, value: str, helper: str) -> None:
    st.markdown(
        f"""
        <div class='metric-card'>
            <div class='metric-label'>{label}</div>
            <div class='metric-value'>{value}</div>
            <div class='metric-delta flat'>{helper}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


kpi_cols = st.columns(5)
with kpi_cols[0]:
    render_metric_card("一级品类数", format_count(_count_unique(filtered_df, "一级品类")), "当前筛选范围")
with kpi_cols[1]:
    render_metric_card("二级品类数", format_count(_count_unique(filtered_df, "二级品类")), "当前筛选范围")
with kpi_cols[2]:
    render_metric_card("三级品类数", format_count(_count_unique(filtered_df, "三级品类")), "当前筛选范围")
with kpi_cols[3]:
    render_metric_card("总入库金额", format_money(total_receipt_amount(filtered_df)), "品类累计规模")
with kpi_cols[4]:
    render_metric_card(
        "降本百分比",
        format_percent(safe_divide(total_costdown_amount_negative(filtered_df), total_receipt_amount(filtered_df))),
        "品类综合表现",
    )

top_n = st.selectbox("二级品类 Top N", ["10", "15", "20", "30"], index=1)
donut_metric = st.radio("结构占比口径", ["总降本金额（负）", "总入库金额"], horizontal=True, key="page4_donut_metric")

row1 = st.columns([1.6, 1])
with row1[0]:
    st.markdown("<div class='card-title'>图表 1：一级品类降本与入库概览</div>", unsafe_allow_html=True)
    st.caption("柱体看规模，折线看降本；适合快速判断哪个一级品类兼具体量和降本贡献。")
    render_clickable_chart(create_category_combo_chart(filtered_df, "一级品类", top_n=12), "page4_chart_level1", "一级品类")
with row1[1]:
    st.markdown("<div class='card-title'>图表 2：一级品类纵向条形图</div>", unsafe_allow_html=True)
    st.caption("柱高表示所选金额口径，颜色表示降本百分比，适合直接比较各一级品类表现。")
    render_clickable_chart(create_category_metric_bar(filtered_df, "一级品类", metric_name=donut_metric, top_n=12), "page4_chart_share", "一级品类")

st.markdown("<div class='card-title'>图表 3：二级品类 Top 降本表现</div>", unsafe_allow_html=True)
st.caption("横向条形图按总降本金额（负）排序，标签同时给出入库金额和降本百分比，便于挑出高价值二级品类。")
render_clickable_chart(create_subcategory_top_chart(filtered_df, top_n=int(top_n)), "page4_chart_level2", "二级品类")

row2 = st.columns(2)
with row2[0]:
    st.markdown("<div class='card-title'>图表 4：一级品类涨价降价数量对比</div>", unsafe_allow_html=True)
    st.caption("按不重复一级品类数量统计涨价/降价分布。")
    st.plotly_chart(create_category_status_donut(filtered_df, "一级品类"), use_container_width=True)
with row2[1]:
    st.markdown("<div class='card-title'>图表 5：二级品类涨价降价数量对比</div>", unsafe_allow_html=True)
    st.caption("按不重复二级品类数量统计涨价/降价分布。")
    st.plotly_chart(create_category_status_donut(filtered_df, "二级品类"), use_container_width=True)

scoped_df = apply_chart_selections(filtered_df, get_page_chart_selections("page4_"))

st.markdown("<div class='section-title'>矩阵 1：一级 → 二级品类月度结构</div>", unsafe_allow_html=True)
render_matrix_table(scoped_df, key="page4_matrix_1", row_fields=["一级品类", "二级品类"], grain="月份", height=480)

if "三级品类" in scoped_df.columns:
    st.markdown("<div class='section-title'>矩阵 2：一级 → 二级 → 三级品类明细</div>", unsafe_allow_html=True)
    render_matrix_table(scoped_df, key="page4_matrix_2", row_fields=["一级品类", "二级品类", "三级品类"], grain="月份", height=520)
