from __future__ import annotations

import streamlit as st

from src.charts import create_sourcing_metric_chart, render_clickable_chart
from src.data_loader import get_clean_data_bundle
from src.filters import apply_chart_selections, apply_global_filters, render_global_sidebar
from src.state import get_page_chart_selections
from src.styles import apply_global_styles
from src.tables import render_matrix_table, render_sourcing_month_matrix
from src.utils import setup_page


setup_page("Sourcing降本情况")
apply_global_styles()

st.markdown("<div class='page-title'>Sourcing降本情况</div>", unsafe_allow_html=True)
st.markdown("<div class='page-subtitle'>按 SOURCING 跟踪时间趋势，并通过矩阵查看供应商与物料粒度明细。</div>", unsafe_allow_html=True)

bundle = get_clean_data_bundle()
render_global_sidebar(bundle)
if bundle.error:
    st.error(bundle.error)
    st.stop()

filtered_df = apply_global_filters(bundle.fact_df, st.session_state.global_filters)
metric_name = st.radio("展示指标", ["降本百分比", "总入库金额", "总降本金额（负）"], horizontal=True, key="page2_metric")
grain = st.radio("时间粒度", ["月份", "周", "日期"], horizontal=True, key="page2_grain")

st.markdown("<div class='card-title'>图表 1：SOURCING 时间趋势</div>", unsafe_allow_html=True)
st.caption("悬浮图表点位可查看：总入库金额、总降本金额（负）、降本百分比、加权平均入库价格。")
render_clickable_chart(create_sourcing_metric_chart(filtered_df, grain, metric_name), "page2_chart_metric", "SOURCING")

scoped_df = apply_chart_selections(filtered_df, get_page_chart_selections("page2_"))
scoped_df = scoped_df.copy()
scoped_df["物料编码名称"] = (
    scoped_df["物料编码"].fillna("").astype(str).str.strip()
    + " | "
    + scoped_df["物料名称"].fillna("").astype(str).str.strip()
)

st.markdown("<div class='section-title'>矩阵 1</div>", unsafe_allow_html=True)
render_matrix_table(scoped_df, key="page2_matrix_1", row_fields=["供应商名称", "物料编码名称"], grain="月份", height=460)

st.markdown("<div class='section-title'>矩阵 2</div>", unsafe_allow_html=True)
st.caption("矩阵2：行=月份，列=SOURCING（每个 SOURCING 下显示四个指标）。")
render_sourcing_month_matrix(scoped_df, key="page2_matrix_2", height=460)
