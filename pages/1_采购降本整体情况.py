from __future__ import annotations

import os
import pandas as pd
import streamlit as st

from src.charts import (
    create_category_donut,
    create_receipt_vs_reduction_chart,
    create_reduction_vs_ratio_chart,
    create_sourcing_ratio_line,
    render_clickable_chart,
)
from src.data_loader import get_clean_data_bundle
from src.filters import apply_chart_selections, apply_global_filters, render_global_sidebar
from src.metrics import aggregate_metrics, compute_mom_delta, total_costdown_amount_negative, total_receipt_amount
from src.state import get_page_chart_selections
from src.styles import apply_global_styles
from src.tables import render_detail_table
from src.utils import format_money, format_percent, safe_divide, setup_page


setup_page("采购降本整体情况")
apply_global_styles()
APP_DEBUG = os.getenv("APP_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}

st.markdown("<div class='page-title'>采购降本整体情况</div>", unsafe_allow_html=True)
st.markdown("<div class='page-subtitle'>总览当前筛选上下文下的入库、降本、类别分布和 SOURCING 走势。</div>", unsafe_allow_html=True)

bundle = get_clean_data_bundle()
render_global_sidebar(bundle)
if bundle.error:
    st.error(bundle.error)
    st.stop()

base_df = bundle.fact_df
filtered_df = apply_global_filters(base_df, st.session_state.global_filters)
comparison_df = apply_global_filters(base_df, st.session_state.global_filters, exclude_fields={"Year", "Quarter", "Month"})


def _debug_overview_source(df: pd.DataFrame, grain: str) -> pd.DataFrame:
    scoped = df.copy()
    for col in ["入库金额", "总降本"]:
        if col in scoped.columns:
            scoped[col] = pd.to_numeric(scoped[col], errors="coerce")

    if grain == "周":
        scoped["时间标签"] = scoped["WeekKey"]
        sort_fields = ["Year", "WeekNo", "时间标签"]
    elif grain == "日期":
        scoped["时间标签"] = scoped["Date"].dt.strftime("%Y-%m-%d")
        sort_fields = ["Date", "时间标签"]
    else:
        scoped["时间标签"] = scoped["Month"]
        sort_fields = ["Year", "MonthNo", "时间标签"]

    grouped = aggregate_metrics(scoped, sort_fields).sort_values(sort_fields).copy()
    grouped["入库金额"] = pd.to_numeric(grouped["入库金额"], errors="coerce")
    grouped["总降本金额（负）"] = pd.to_numeric(grouped["总降本金额（负）"], errors="coerce")
    grouped["降本百分比"] = pd.to_numeric(grouped["降本百分比"], errors="coerce")
    grouped["时间标签"] = grouped["时间标签"].astype(str)
    return grouped[["时间标签", "入库金额", "总降本金额（负）", "降本百分比"]]


def render_metric_card(label: str, value: str, delta_value: float | None) -> None:
    if delta_value is None:
        delta_class = "flat"
        delta_text = "环比 --"
    elif delta_value > 0:
        delta_class = "up"
        delta_text = f"↑ 环比 {format_percent(delta_value)}"
    elif delta_value < 0:
        delta_class = "down"
        delta_text = f"↓ 环比 {format_percent(delta_value)}"
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


kpi_cols = st.columns(5)
with kpi_cols[0]:
    render_metric_card(
        "总入库金额",
        format_money(total_receipt_amount(filtered_df)),
        compute_mom_delta("总入库金额", filtered_df, comparison_df),
    )
with kpi_cols[1]:
    render_metric_card(
        "降本百分比",
        format_percent(safe_divide(-filtered_df["总降本"].sum(), filtered_df["入库金额"].sum())),
        compute_mom_delta("降本百分比", filtered_df, comparison_df),
    )
with kpi_cols[2]:
    render_metric_card(
        "总降本金额（负）",
        format_money(total_costdown_amount_negative(filtered_df)),
        compute_mom_delta("总降本金额（负）", filtered_df, comparison_df),
    )
with kpi_cols[3]:
    render_metric_card(
        "供应商涨价金额",
        format_money(filtered_df.loc[filtered_df["降本类别"] == "涨价", "总降本"].sum()),
        compute_mom_delta("供应商涨价金额", filtered_df, comparison_df),
    )
with kpi_cols[4]:
    render_metric_card(
        "供应商降价金额",
        format_money(filtered_df.loc[filtered_df["降本类别"] == "降价", "总降本"].sum()),
        compute_mom_delta("供应商降价金额", filtered_df, comparison_df),
    )

chart_grain = st.radio("时间粒度", ["月份", "周", "日期"], horizontal=True, key="page1_grain")

fig_combo_1 = create_receipt_vs_reduction_chart(filtered_df, chart_grain)
fig_combo_2 = create_reduction_vs_ratio_chart(filtered_df, chart_grain)

row1 = st.columns(2)
with row1[0]:
    st.markdown("<div class='card-title'>组合图 1</div>", unsafe_allow_html=True)
    render_clickable_chart(fig_combo_1, "page1_chart_receipt", "Month")
with row1[1]:
    st.markdown("<div class='card-title'>组合图 2</div>", unsafe_allow_html=True)
    render_clickable_chart(fig_combo_2, "page1_chart_ratio", "Month")

row2 = st.columns(2)
with row2[0]:
    st.markdown("<div class='card-title'>图表 3：降本类别圆环图</div>", unsafe_allow_html=True)
    render_clickable_chart(create_category_donut(filtered_df), "page1_chart_donut", "降本类别")
with row2[1]:
    st.markdown("<div class='card-title'>图表 4：SOURCING 降本百分比走势</div>", unsafe_allow_html=True)
    render_clickable_chart(create_sourcing_ratio_line(filtered_df, chart_grain), "page1_chart_sourcing", "SOURCING")

if APP_DEBUG:
    with st.expander("调试：查看图表聚合源数据（用于核对卡片与图表口径）", expanded=False):
        debug_df = _debug_overview_source(filtered_df, chart_grain).copy()
        debug_df["入库金额"] = debug_df["入库金额"].round(2)
        debug_df["总降本金额（负）"] = debug_df["总降本金额（负）"].round(2)
        debug_df["降本百分比"] = (debug_df["降本百分比"] * 100).round(4)
        st.caption("降本百分比列显示为百分数（%），便于人工核对。")
        st.dataframe(debug_df.rename(columns={"降本百分比": "降本百分比(%)"}), use_container_width=True, hide_index=True)

        st.caption("图表1 Trace 样本（前 5 个）")
        st.write(
            {
                "bar_x": list(fig_combo_1.data[0].x[:5]) if len(fig_combo_1.data) > 0 else [],
                "bar_y": list(fig_combo_1.data[0].y[:5]) if len(fig_combo_1.data) > 0 else [],
                "line_y": list(fig_combo_1.data[1].y[:5]) if len(fig_combo_1.data) > 1 else [],
                "bar_orientation": getattr(fig_combo_1.data[0], "orientation", None) if len(fig_combo_1.data) > 0 else None,
                "bar_y_dtype": str(pd.Series(fig_combo_1.data[0].y).dtype) if len(fig_combo_1.data) > 0 else None,
                "line_y_dtype": str(pd.Series(fig_combo_1.data[1].y).dtype) if len(fig_combo_1.data) > 1 else None,
            }
        )

        st.caption("图表2 Trace 样本（前 5 个）")
        st.write(
            {
                "bar_x": list(fig_combo_2.data[0].x[:5]) if len(fig_combo_2.data) > 0 else [],
                "bar_y": list(fig_combo_2.data[0].y[:5]) if len(fig_combo_2.data) > 0 else [],
                "line_y": list(fig_combo_2.data[1].y[:5]) if len(fig_combo_2.data) > 1 else [],
                "bar_orientation": getattr(fig_combo_2.data[0], "orientation", None) if len(fig_combo_2.data) > 0 else None,
                "bar_y_dtype": str(pd.Series(fig_combo_2.data[0].y).dtype) if len(fig_combo_2.data) > 0 else None,
                "line_y_dtype": str(pd.Series(fig_combo_2.data[1].y).dtype) if len(fig_combo_2.data) > 1 else None,
            }
        )

st.markdown("<div class='section-title'>联动明细表</div>", unsafe_allow_html=True)
page_selection_df = apply_chart_selections(filtered_df, get_page_chart_selections("page1_"))
render_detail_table(page_selection_df, key="page1_detail_table", height=420)


