from __future__ import annotations

import streamlit as st

from src.charts import create_supplier_cluster_chart, render_clickable_chart
from src.data_loader import get_clean_data_bundle
from src.filters import apply_chart_selections, apply_global_filters, render_global_sidebar
from src.metrics import compute_mom_delta, discount_supplier_count, increase_supplier_count
from src.state import get_page_chart_selections
from src.styles import apply_global_styles
from src.tables import render_matrix_table
from src.utils import format_count, setup_page


setup_page("各供应商降本情况")
apply_global_styles()

st.markdown("<div class='page-title'>各供应商降本情况</div>", unsafe_allow_html=True)
st.markdown("<div class='page-subtitle'>查看不同供应商在涨价、降价和综合降本上的贡献，并联动到明细矩阵。</div>", unsafe_allow_html=True)

bundle = get_clean_data_bundle()
render_global_sidebar(bundle)
if bundle.error:
    st.error(bundle.error)
    st.stop()

base_df = bundle.fact_df
filtered_df = apply_global_filters(base_df, st.session_state.global_filters)
comparison_df = apply_global_filters(base_df, st.session_state.global_filters, exclude_fields={"Year", "Quarter", "Month"})


def render_metric_card(label: str, value: str, delta_value: float | None) -> None:
    if delta_value is None:
        delta_class = "flat"
        delta_text = "环比 --"
    elif delta_value > 0:
        delta_class = "up"
        delta_text = f"↑ 环比 {delta_value * 100:,.2f}%"
    elif delta_value < 0:
        delta_class = "down"
        delta_text = f"↓ 环比 {delta_value * 100:,.2f}%"
    else:
        delta_class = "flat"
        delta_text = "环比 0.00%"
    st.markdown(
        f"""
        <div class='metric-card'>
            <div class='metric-label'>{label}</div>
            <div class='metric-value'>{value}</div>
            <div class='metric-delta {delta_class}'>{delta_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


kpi_cols = st.columns(2)
with kpi_cols[0]:
    render_metric_card(
        "降本供应商数量",
        format_count(discount_supplier_count(filtered_df)),
        compute_mom_delta("降价供应商数", filtered_df, comparison_df),
    )
with kpi_cols[1]:
    render_metric_card(
        "涨价供应商数量",
        format_count(increase_supplier_count(filtered_df)),
        compute_mom_delta("涨价供应商数", filtered_df, comparison_df),
    )

top_n = st.selectbox("Top N", ["10", "20", "50", "全部"], index=1)
st.markdown("<div class='card-title'>图表 1：供应商簇状横向柱状图</div>", unsafe_allow_html=True)
st.caption("悬浮柱体可查看：总降本金额（负）、供应链降价金额（负）、供应商涨价金额、总入库金额、降本百分比。")
render_clickable_chart(create_supplier_cluster_chart(filtered_df, top_n), "page3_chart_supplier", "供应商名称")

scoped_df = apply_chart_selections(filtered_df, get_page_chart_selections("page3_"))
scoped_df = scoped_df.copy()
scoped_df["物料编码名称"] = (
    scoped_df["物料编码"].fillna("").astype(str).str.strip()
    + " | "
    + scoped_df["物料名称"].fillna("").astype(str).str.strip()
)

st.markdown("<div class='section-title'>矩阵 1</div>", unsafe_allow_html=True)
render_matrix_table(scoped_df, key="page3_matrix_1", row_fields=["物料编码名称", "供应商名称"], grain="月份", height=460)

st.markdown("<div class='section-title'>矩阵 2</div>", unsafe_allow_html=True)
render_matrix_table(scoped_df, key="page3_matrix_2", row_fields=["供应商名称", "物料编码名称"], grain="月份", height=460)


