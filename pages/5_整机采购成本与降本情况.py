from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.charts import render_clickable_chart
from src.machine_costdown import get_machine_costdown_bundle
from src.state import get_page_chart_selections
from src.styles import apply_global_styles
from src.tables import render_machine_cost_matrix
from src.utils import format_count, format_money, format_percent, setup_page


setup_page("整机采购成本与降本情况")
apply_global_styles()

st.markdown("<div class='page-title'>整机采购成本与降本情况</div>", unsafe_allow_html=True)
st.markdown("<div class='page-subtitle'>按真实采购停点统计整机的采购入库成本、涨降价与降本表现。</div>", unsafe_allow_html=True)

bundle = get_machine_costdown_bundle()

with st.sidebar:
    st.markdown("## 整机成本分析")
    if st.button("刷新整机数据", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()

if bundle.error:
    st.error(bundle.error)
    st.stop()

summary_df = bundle.summary_df.copy()
time_df = bundle.time_df.copy()
detail_df = bundle.detail_df.copy()
unpriced_df = bundle.unpriced_df.copy()

if summary_df.empty:
    st.warning("当前没有可展示的整机采购成本数据。")
    st.stop()

product_lines = sorted(summary_df["产品线"].dropna().astype(str).unique().tolist())
selected_lines = st.sidebar.multiselect("产品线", options=product_lines, default=product_lines, key="page5_lines")
if selected_lines:
    summary_df = summary_df[summary_df["产品线"].isin(selected_lines)].copy()
    detail_df = detail_df[detail_df["产品线"].isin(selected_lines)].copy()
    unpriced_df = unpriced_df[unpriced_df["产品线"].isin(selected_lines)].copy()

summary_df["整机标签"] = summary_df["物料名称"].fillna("").astype(str)
detail_df["采购停点物料"] = detail_df["采购层级物料编码"].fillna("").astype(str) + " | " + detail_df["采购层级物料名称"].fillna("").astype(str)


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


def create_machine_overview_chart(df: pd.DataFrame, product_name: str | None = None, show_all: bool = False) -> go.Figure:
    scoped = df.dropna(subset=["Month"]).copy().sort_values(["Year", "MonthNo", "物料名称"])
    fig = go.Figure()
    if not show_all and product_name:
        scoped = scoped[scoped["物料名称"].astype(str) == str(product_name)].copy()

    if scoped.empty:
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#E2E8F0"),
            height=420,
            margin=dict(l=70, r=70, t=40, b=40),
        )
        return fig

    products = scoped.groupby("物料名称", dropna=False) if show_all else [(product_name or "", scoped)]
    for current_name, product_df in products:
        line_text = (
            [
                f"入库 {cost:,.2f}<br>降本 {reduction:,.2f}<br>{ratio:.2%}"
                if pd.notna(cost) and pd.notna(reduction) and pd.notna(ratio)
                else "--"
                for cost, reduction, ratio in zip(product_df["整机总入库成本"], product_df["整机总降本金额（负）"], product_df["整机降本百分比"])
            ]
            if not show_all
            else None
        )
        fig.add_trace(
            go.Bar(
                x=product_df["Month"],
                y=product_df["整机总入库成本"],
                name=f"{current_name} - 入库成本" if show_all else "整机总入库成本",
                marker_color="#38bdf8" if not show_all else None,
                text=[f"{v:,.2f}" if pd.notna(v) else "--" for v in product_df["整机总入库成本"]],
                textposition="outside",
                customdata=product_df[["整机总降本金额（负）", "整机降本百分比"]].values,
                hovertemplate="月份=%{x}<br>整机总入库成本=%{y:,.2f}<br>整机总降本金额（负）=%{customdata[0]:,.2f}<br>整机降本百分比=%{customdata[1]:.2%}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=product_df["Month"],
                y=product_df["整机总降本金额（负）"],
                name=f"{current_name} - 降本金额" if show_all else "整机总降本金额（负）",
                mode="lines+markers+text",
                line=dict(color="#22c55e", width=3) if not show_all else dict(width=3),
                text=line_text,
                textposition="top center",
                yaxis="y2",
                customdata=product_df[["整机总入库成本", "整机降本百分比"]].values,
                hovertemplate="月份=%{x}<br>整机总降本金额（负）=%{y:,.2f}<br>整机总入库成本=%{customdata[0]:,.2f}<br>整机降本百分比=%{customdata[1]:.2%}<extra></extra>",
            )
        )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E2E8F0"),
        height=420,
        margin=dict(l=70, r=70, t=40, b=40),
        hovermode="x unified",
        yaxis=dict(title="整机总入库成本", tickformat=",.0f", gridcolor="rgba(148,163,184,0.15)"),
        yaxis2=dict(title="整机总降本金额（负）", overlaying="y", side="right", tickformat=",.0f"),
    )
    fig.update_xaxes(type="category", showgrid=False)
    return fig


def create_component_cost_chart(df: pd.DataFrame, top_n: int = 15) -> go.Figure:
    scoped = df.sort_values("单机总入库成本", ascending=False).head(top_n).copy()
    fig = go.Figure(
        go.Bar(
            y=scoped["采购停点物料"],
            x=scoped["单机总入库成本"],
            orientation="h",
            marker=dict(color=scoped["单机降本百分比"], colorscale=[[0, "#fb7185"], [0.5, "#38bdf8"], [1, "#22c55e"]], colorbar=dict(title="降本百分比", tickformat=".1%")),
            text=[f"{c:,.0f} | {r:.2%}" if pd.notna(c) and pd.notna(r) else f"{c:,.0f}" for c, r in zip(scoped["单机总入库成本"], scoped["单机降本百分比"])],
            textposition="outside",
            customdata=scoped[["主供应商", "单机总降本金额（负）", "单机涨价金额", "单机降价金额（负）"]].values,
            hovertemplate="采购停点物料=%{y}<br>单机总入库成本=%{x:,.2f}<br>主供应商=%{customdata[0]}<br>单机总降本金额（负）=%{customdata[1]:,.2f}<br>单机涨价金额=%{customdata[2]:,.2f}<br>单机降价金额（负）=%{customdata[3]:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E2E8F0"),
        height=max(420, len(scoped) * 30),
        margin=dict(l=70, r=70, t=40, b=40),
    )
    fig.update_xaxes(tickformat=",.0f", gridcolor="rgba(148,163,184,0.15)")
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return fig


def create_supplier_chart(df: pd.DataFrame) -> go.Figure:
    grouped = (
        df.groupby("主供应商", dropna=False)
        .agg(**{"单机总入库成本": ("单机总入库成本", "sum"), "单机总降本金额（负）": ("单机总降本金额（负）", "sum")})
        .reset_index()
        .sort_values("单机总入库成本", ascending=False)
        .head(12)
    )
    fig = go.Figure()
    fig.add_trace(go.Bar(x=grouped["主供应商"], y=grouped["单机总入库成本"], name="单机总入库成本", marker_color="#60a5fa"))
    fig.add_trace(go.Bar(x=grouped["主供应商"], y=grouped["单机总降本金额（负）"], name="单机总降本金额（负）", marker_color="#22c55e"))
    fig.update_layout(
        barmode="group",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E2E8F0"),
        height=420,
        margin=dict(l=70, r=40, t=40, b=40),
    )
    fig.update_xaxes(type="category", showgrid=False)
    fig.update_yaxes(tickformat=",.0f", gridcolor="rgba(148,163,184,0.15)")
    return fig


kpi_cols = st.columns(5)
with kpi_cols[0]:
    render_metric_card("整机数量", format_count(len(summary_df)), "当前分析范围")
with kpi_cols[1]:
    render_metric_card("总入库成本", format_money(summary_df["整机总入库成本"].sum()), "所选整机合计")
with kpi_cols[2]:
    render_metric_card("总降本金额（负）", format_money(summary_df["整机总降本金额（负）"].sum()), "所选整机合计")
with kpi_cols[3]:
    total_ratio = summary_df["整机总降本金额（负）"].sum() / summary_df["整机总入库成本"].replace({0: pd.NA}).sum()
    render_metric_card("综合降本百分比", format_percent(total_ratio), "所选整机合计")
with kpi_cols[4]:
    render_metric_card("无价停点物料数", format_count(summary_df["无价停点物料数"].sum()), "需补价格映射")

machine_options = summary_df["物料名称"].astype(str).tolist()
selected_machine = st.selectbox("选择产品", options=machine_options, index=0)
chart_mode = st.radio("图表1视图", ["当前产品", "全部产品"], horizontal=True, key="page5_chart1_mode")

title = "图表 1：当前产品整机入库成本与降本总金额随时间变化" if chart_mode == "当前产品" else "图表 1：全部产品整机入库成本与降本总金额随时间变化"
caption = "仅展示当前选中产品；数据标签包含入库成本、降本金额和降本百分比。" if chart_mode == "当前产品" else "展示全部产品放在一起的时间变化；数据标签包含入库成本、降本金额和降本百分比。"
st.markdown(f"<div class='card-title'>{title}</div>", unsafe_allow_html=True)
st.caption(caption)
st.plotly_chart(create_machine_overview_chart(time_df, selected_machine, show_all=chart_mode == "全部产品"), use_container_width=True)

page_selections = get_page_chart_selections("page5_")

selected_summary = summary_df[summary_df["物料名称"].astype(str) == str(selected_machine)].copy()
selected_detail = detail_df[detail_df["产品"].astype(str) == str(selected_machine)].copy()
selected_unpriced = unpriced_df[unpriced_df["产品"].astype(str) == str(selected_machine)].copy()

if selected_summary.empty:
    st.warning("当前没有命中的整机汇总结果。")
    st.stop()

machine_row = selected_summary.iloc[0]
focus_cols = st.columns(4)
with focus_cols[0]:
    render_metric_card("当前产品", machine_row["物料名称"], machine_row["产品线"])
with focus_cols[1]:
    render_metric_card("整机总入库成本", format_money(machine_row["整机总入库成本"]), str(machine_row["产品线"]))
with focus_cols[2]:
    render_metric_card("整机总降本金额（负）", format_money(machine_row["整机总降本金额（负）"]), "整机口径")
with focus_cols[3]:
    render_metric_card("整机降本百分比", format_percent(machine_row["整机降本百分比"]), f"停点物料 {int(machine_row['采购停点物料数'])} 个")

row2 = st.columns(2)
with row2[0]:
    st.markdown("<div class='card-title'>图表 2：采购停点物料 Top 成本贡献</div>", unsafe_allow_html=True)
    st.caption("停点物料：沿 BOM 往下展开时，第一次在采购入库成本表里能直接命中的物料；到这里就停止继续下钻，并按它来计入整机成本。")
    render_clickable_chart(create_component_cost_chart(selected_detail), "page5_chart_component", "采购停点物料")
with row2[1]:
    st.markdown("<div class='card-title'>图表 3：供应商贡献分布</div>", unsafe_allow_html=True)
    st.plotly_chart(create_supplier_chart(selected_detail), use_container_width=True)

if "page5_chart_component" in page_selections:
    selected_component = str(page_selections["page5_chart_component"].get("value") or "").strip()
    selected_detail = selected_detail[selected_detail["采购停点物料"].astype(str) == selected_component].copy()

st.markdown("<div class='section-title'>整机采购成本矩阵</div>", unsafe_allow_html=True)
render_machine_cost_matrix(detail_df, key="page5_machine_matrix", height=560)

with st.expander("查看未命中采购价格的 BOM 停点物料", expanded=False):
    if selected_unpriced.empty:
        st.success("当前整机所有停点物料都已在采购成本表中命中。")
    else:
        st.dataframe(selected_unpriced, use_container_width=True, hide_index=True)

st.caption(
    f"BOM来源：{bundle.source_info['bom_path']} | 物料主数据：{bundle.source_info['material_master_path']} | 采购成本来源：{bundle.source_info['purchase_costdown_path']} | 价目表：{bundle.source_info.get('cost_table_url', '') or '未配置'}"
)
