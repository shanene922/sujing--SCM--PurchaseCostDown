from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from .metrics import aggregate_metrics
from .state import toggle_chart_selection


PLOT_BG = "rgba(0,0,0,0)"
FONT_COLOR = "#E2E8F0"
GRID_COLOR = "rgba(148,163,184,0.15)"



def _apply_layout(fig: go.Figure, title: str, height: int = 380) -> go.Figure:
    fig.update_layout(
        title=title,
        paper_bgcolor=PLOT_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(color=FONT_COLOR, size=12),
        height=height,
        margin=dict(l=90, r=80, t=55, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR)
    return fig



def _ensure_metric_numeric(df: pd.DataFrame) -> pd.DataFrame:
    scoped = df.copy()
    metric_cols = ["入库金额", "入库数量", "总降本", "总降本金额（负）", "降本百分比", "加权平均入库价格"]
    for col in metric_cols:
        if col in scoped.columns:
            scoped[col] = (
                scoped[col]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace("%", "", regex=False)
                .replace({"None": pd.NA, "nan": pd.NA, "": pd.NA})
            )
            scoped[col] = pd.to_numeric(scoped[col], errors="coerce")
    return scoped



def _coerce_plot_series(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    coerced = df.copy()
    for col in columns:
        if col in coerced.columns:
            coerced[col] = pd.to_numeric(coerced[col], errors="coerce").astype("float64")
    return coerced


def _format_short_money(value: float) -> str:
    if pd.isna(value):
        return "--"
    abs_value = abs(float(value))
    if abs_value >= 100000000:
        return f"{value / 100000000:.2f}亿"
    if abs_value >= 10000:
        return f"{value / 10000:.1f}万"
    return f"{value:,.0f}"



def _time_bucket(df: pd.DataFrame, grain: str) -> tuple[str, list[str]]:
    if grain == "周":
        df["时间标签"] = df["WeekKey"]
        return "WeekKey", ["Year", "WeekNo", "时间标签"]
    if grain == "日期":
        df["时间标签"] = df["Date"].dt.strftime("%Y-%m-%d")
        return "Date", ["Date", "时间标签"]
    df["时间标签"] = df["Month"]
    return "Month", ["Year", "MonthNo", "时间标签"]


def build_overview_combo_source(df: pd.DataFrame, grain: str) -> pd.DataFrame:
    scoped = _ensure_metric_numeric(df)
    _, sort_fields = _time_bucket(scoped, grain)
    grouped = aggregate_metrics(scoped, sort_fields).sort_values(sort_fields).copy()
    grouped = _coerce_plot_series(grouped, ["入库金额", "总降本", "总降本金额（负）", "降本百分比"])
    grouped["时间标签"] = grouped["时间标签"].astype(str)
    return grouped[["时间标签", "入库金额", "总降本金额（负）", "降本百分比"]]



def render_clickable_chart(fig: go.Figure, key: str, field: str) -> None:
    # Use native streamlit chart rendering for stable visuals.
    st.plotly_chart(fig, use_container_width=True, key=f"{key}_plot")

    # Fallback linked-filter control (stable replacement for flaky click events).
    values: list[str] = []
    if len(fig.data) > 0:
        trace0 = fig.data[0]
        orientation = getattr(trace0, "orientation", None)
        if orientation == "h":
            # Horizontal bar chart: category dimension is on y-axis.
            raw = getattr(trace0, "y", None)
        else:
            raw = getattr(trace0, "x", None)
        if raw is None or len(raw) == 0:
            raw = getattr(trace0, "labels", None)
        if raw is not None:
            values = [str(v) for v in raw if v is not None and str(v) != ""]
    uniq_values = list(dict.fromkeys(values))
    options = ["(全部)"] + uniq_values
    selected = st.selectbox(
        "选中维度明细",
        options=options,
        key=f"{key}_selector",
        index=0,
        help="用于替代图表点击联动；选择后将联动下方表格/矩阵。",
    )
    if selected == "(全部)":
        if "chart_selections" in st.session_state and key in st.session_state.chart_selections:
            st.session_state.chart_selections.pop(key, None)
    else:
        toggle_chart_selection(key, {"field": field, "value": selected, "label": selected})



def create_receipt_vs_reduction_chart(df: pd.DataFrame, grain: str) -> go.Figure:
    scoped = _ensure_metric_numeric(df)
    selection_field, sort_fields = _time_bucket(scoped, grain)
    grouped = aggregate_metrics(scoped, sort_fields).sort_values(sort_fields)
    grouped = _coerce_plot_series(grouped, ["入库金额", "总降本金额（负）", "降本百分比"])
    x_values = grouped["时间标签"].astype(str) if grain != "日期" else grouped["时间标签"]
    customdata = [[selection_field, value] for value in grouped["时间标签"]]
    label_text = [
        (
            f"入库 {_format_short_money(receipt)}<br>降本 {_format_short_money(amount)}<br>{ratio:.2%}"
            if pd.notna(receipt) and pd.notna(amount) and pd.notna(ratio)
            else (
                f"入库 {_format_short_money(receipt)}<br>降本 {_format_short_money(amount)}"
                if pd.notna(receipt) and pd.notna(amount)
                else _format_short_money(receipt if pd.notna(receipt) else amount)
            )
        )
        for receipt, amount, ratio in zip(grouped["入库金额"], grouped["总降本金额（负）"], grouped["降本百分比"])
    ]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=x_values,
            y=grouped["入库金额"],
            name="总入库金额",
            orientation="v",
            marker_color="#38bdf8",
            customdata=customdata,
            hovertemplate="时间=%{x}<br>总入库金额=%{y:,.2f}<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=grouped["总降本金额（负）"],
            name="总降本金额（负）",
            mode="lines+markers",
            line=dict(color="#22c55e", width=3),
            customdata=customdata,
            hovertemplate="时间=%{x}<br>总降本金额（负）=%{y:,.2f}<br>降本百分比=%{customdata[2]:.2%}<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.update_traces(
        selector=dict(name="总降本金额（负）"),
        customdata=[[selection_field, value, ratio] for value, ratio in zip(grouped["时间标签"], grouped["降本百分比"])],
    )
    bar_max = float(grouped["入库金额"].max()) if len(grouped) and pd.notna(grouped["入库金额"].max()) else 0.0
    line_max = float(grouped["总降本金额（负）"].max()) if len(grouped) and pd.notna(grouped["总降本金额（负）"].max()) else 0.0
    fig.update_yaxes(
        title_text="总入库金额",
        secondary_y=False,
        tickformat=",.2f",
        separatethousands=True,
        showexponent="none",
        range=[0, bar_max * 1.15 if bar_max > 0 else 1],
    )
    fig.update_yaxes(
        title_text="总降本金额（负）",
        secondary_y=True,
        tickformat=",.2f",
        separatethousands=True,
        showexponent="none",
        range=[0, line_max * 1.28 if line_max > 0 else 1],
    )
    if grain != "日期":
        fig.update_xaxes(type="category")
    for x_value, bar_value, text in zip(x_values, grouped["入库金额"], label_text):
        if pd.isna(bar_value):
            continue
        fig.add_annotation(
            x=x_value,
            y=bar_value,
            text=text,
            showarrow=False,
            yshift=14,
            xanchor="center",
            yanchor="bottom",
            font=dict(color=FONT_COLOR, size=11),
            align="center",
        )
    return _apply_layout(fig, "总入库金额 vs 总降本金额（负）")



def create_reduction_vs_ratio_chart(df: pd.DataFrame, grain: str) -> go.Figure:
    scoped = _ensure_metric_numeric(df)
    selection_field, sort_fields = _time_bucket(scoped, grain)
    grouped = aggregate_metrics(scoped, sort_fields).sort_values(sort_fields)
    grouped = _coerce_plot_series(grouped, ["总降本金额（负）", "降本百分比"])
    x_values = grouped["时间标签"].astype(str) if grain != "日期" else grouped["时间标签"]
    customdata = [[selection_field, value] for value in grouped["时间标签"]]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=x_values,
            y=grouped["总降本金额（负）"],
            name="总降本金额（负）",
            orientation="v",
            marker_color="#22c55e",
            customdata=customdata,
            hovertemplate="时间=%{x}<br>总降本金额（负）=%{y:,.2f}<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=grouped["降本百分比"],
            name="降本百分比",
            mode="lines+markers",
            line=dict(color="#f59e0b", width=3),
            customdata=customdata,
            hovertemplate="时间=%{x}<br>降本百分比=%{y:.2%}<extra></extra>",
        ),
        secondary_y=True,
    )
    bar_max = float(grouped["总降本金额（负）"].max()) if len(grouped) and pd.notna(grouped["总降本金额（负）"].max()) else 0.0
    ratio_max = float(grouped["降本百分比"].max()) if len(grouped) and pd.notna(grouped["降本百分比"].max()) else 0.0
    fig.update_yaxes(
        title_text="总降本金额（负）",
        secondary_y=False,
        tickformat=",.2f",
        separatethousands=True,
        showexponent="none",
        range=[0, bar_max * 1.15 if bar_max > 0 else 1],
    )
    fig.update_yaxes(
        title_text="降本百分比",
        tickformat=".2%",
        secondary_y=True,
        range=[0, ratio_max * 1.2 if ratio_max > 0 else 0.01],
    )
    if grain != "日期":
        fig.update_xaxes(type="category")
    return _apply_layout(fig, "总降本金额（负） vs 降本百分比")



def create_category_donut(df: pd.DataFrame) -> go.Figure:
    grouped = (
        df.groupby("降本类别", dropna=False)["物料编码"]
        .nunique()
        .reset_index(name="物料编码数")
        .sort_values("物料编码数", ascending=False)
    )
    customdata = [["降本类别", value] for value in grouped["降本类别"].fillna("(空值)")]
    fig = go.Figure(
        go.Pie(
            labels=grouped["降本类别"].fillna("(空值)"),
            values=grouped["物料编码数"],
            hole=0.62,
            marker=dict(colors=["#38bdf8", "#22c55e", "#f97316", "#94a3b8", "#fb7185"]),
            customdata=customdata,
            hovertemplate="%{label}<br>物料编码数=%{value}<br>占比=%{percent}<extra></extra>",
        )
    )
    fig = _apply_layout(fig, "降本类别物料分布", height=380)
    fig.update_layout(
        legend=dict(orientation="v", yanchor="top", y=1.0, xanchor="left", x=1.02),
        margin=dict(l=40, r=140, t=55, b=40),
    )
    return fig


def create_category_status_donut(df: pd.DataFrame, level: str) -> go.Figure:
    if level not in df.columns or "降本类别" not in df.columns:
        return _apply_layout(go.Figure(), f"{level}涨价降价数量对比", height=380)

    grouped = (
        df[df["降本类别"].astype(str).isin(["涨价", "降价"])]
        .groupby("降本类别", dropna=False)[level]
        .nunique()
        .reset_index(name="不重复数量")
        .sort_values("不重复数量", ascending=False)
    )
    if grouped.empty:
        return _apply_layout(go.Figure(), f"{level}涨价降价数量对比", height=380)

    color_map = {"降价": "#22c55e", "涨价": "#f97316"}
    fig = go.Figure(
        go.Pie(
            labels=grouped["降本类别"].fillna("(空值)"),
            values=grouped["不重复数量"],
            hole=0.62,
            marker=dict(colors=[color_map.get(str(v), "#94a3b8") for v in grouped["降本类别"]]),
            hovertemplate="%{label}<br>不重复数量=%{value}<br>占比=%{percent}<extra></extra>",
            textinfo="label+value",
        )
    )
    fig = _apply_layout(fig, f"{level}涨价降价数量对比", height=380)
    fig.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(l=40, r=40, t=55, b=40),
    )
    return fig


def create_sourcing_ratio_line(df: pd.DataFrame, grain: str) -> go.Figure:
    scoped = _ensure_metric_numeric(df)
    _, sort_fields = _time_bucket(scoped, grain)
    grouped = aggregate_metrics(scoped, ["SOURCING", *sort_fields]).sort_values(["SOURCING", *sort_fields])
    grouped = _coerce_plot_series(grouped, ["入库金额", "总降本金额（负）", "降本百分比", "加权平均入库价格"])

    fig = go.Figure()
    for source, source_df in grouped.groupby("SOURCING", dropna=False):
        x_values = source_df["时间标签"].astype(str) if grain != "日期" else source_df["时间标签"]
        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=source_df["降本百分比"],
                name=str(source),
                mode="lines+markers",
                hovertemplate=(
                    f"SOURCING={source}<br>"
                    "时间=%{x}<br>"
                    "降本百分比=%{y:.2%}<extra></extra>"
                ),
            )
        )

    fig.update_yaxes(tickformat=".2%")
    if grain != "日期":
        fig.update_xaxes(type="category")
    return _apply_layout(fig, "各 SOURCING 降本百分比走势")



def create_sourcing_metric_chart(df: pd.DataFrame, grain: str, metric_name: str) -> go.Figure:
    scoped = _ensure_metric_numeric(df)
    _, sort_fields = _time_bucket(scoped, grain)
    grouped = aggregate_metrics(scoped, ["SOURCING", *sort_fields]).sort_values(["SOURCING", *sort_fields])
    grouped = _coerce_plot_series(grouped, ["入库金额", "总降本金额（负）", "降本百分比", "加权平均入库价格"])
    metric_column = "入库金额" if metric_name == "总入库金额" else metric_name

    fig = go.Figure()
    for source, source_df in grouped.groupby("SOURCING", dropna=False):
        x_values = source_df["时间标签"].astype(str) if grain != "日期" else source_df["时间标签"]
        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=source_df[metric_column],
                name=str(source),
                mode="lines+markers",
                hovertemplate=(
                    f"SOURCING={source}<br>"
                    "时间=%{x}<br>"
                    f"{metric_name}=" + ("%{y:.2%}" if metric_name == "降本百分比" else "%{y:,.2f}") + "<extra></extra>"
                ),
            )
        )

    if metric_name == "降本百分比":
        fig.update_yaxes(tickformat=".2%")
    else:
        fig.update_yaxes(tickformat=",.2f")
    if grain != "日期":
        fig.update_xaxes(type="category")
    return _apply_layout(fig, f"SOURCING 趋势 - {metric_name}")



def create_supplier_cluster_chart(df: pd.DataFrame, top_n: str) -> go.Figure:
    scoped = _ensure_metric_numeric(df)
    grouped = (
        scoped.groupby("供应商名称", dropna=False)
        .agg(
            总降本=("总降本", "sum"),
            入库金额=("入库金额", "sum"),
            供应商涨价金额=("总降本", lambda s: s[scoped.loc[s.index, "降本类别"] == "涨价"].sum()),
            供应商降价金额=("总降本", lambda s: s[scoped.loc[s.index, "降本类别"] == "降价"].sum()),
        )
        .reset_index()
    )
    grouped["总降本金额（负）"] = -grouped["总降本"]
    grouped["供应链降价金额（负）"] = -grouped["供应商降价金额"]
    grouped["降本百分比"] = grouped["总降本金额（负）"] / grouped["入库金额"].replace({0: pd.NA})
    grouped = grouped.sort_values("总降本金额（负）", ascending=False)
    if top_n != "全部":
        grouped = grouped.head(int(top_n))

    fig = go.Figure()
    tooltip = (
        "供应商=%{y}<br>"
        "当前系列值=%{x:,.2f}<br>"
        "总降本金额（负）=%{customdata[0]:,.2f}<br>"
        "供应链降价金额（负）=%{customdata[1]:,.2f}<br>"
        "供应商涨价金额=%{customdata[2]:,.2f}<br>"
        "总入库金额=%{customdata[3]:,.2f}<br>"
        "降本百分比=%{customdata[4]:.2%}<extra></extra>"
    )
    customdata = grouped[["总降本金额（负）", "供应链降价金额（负）", "供应商涨价金额", "入库金额", "降本百分比"]].values

    fig.add_trace(
        go.Bar(
            y=grouped["供应商名称"],
            x=grouped["总降本金额（负）"],
            name="总降本金额（负）",
            orientation="h",
            marker_color="#38bdf8",
            customdata=customdata,
            hovertemplate=tooltip,
        )
    )
    fig.add_trace(
        go.Bar(
            y=grouped["供应商名称"],
            x=grouped["供应链降价金额（负）"],
            name="供应链降价金额（负）",
            orientation="h",
            marker_color="#22c55e",
            customdata=customdata,
            hovertemplate=tooltip,
        )
    )
    fig.add_trace(
        go.Bar(
            y=grouped["供应商名称"],
            x=grouped["供应商涨价金额"],
            name="供应商涨价金额",
            orientation="h",
            marker_color="#f97316",
            customdata=customdata,
            hovertemplate=tooltip,
        )
    )
    fig.update_layout(barmode="group")
    return _apply_layout(fig, "各供应商降本表现", height=max(420, len(grouped) * 28))


def create_category_combo_chart(df: pd.DataFrame, level: str, top_n: int = 12) -> go.Figure:
    scoped = _ensure_metric_numeric(df)
    grouped = aggregate_metrics(scoped, [level]).rename(columns={"入库金额": "总入库金额"})
    grouped[level] = grouped[level].fillna("(空值)").astype(str)
    grouped = grouped.sort_values("总降本金额（负）", ascending=False).head(top_n).copy()
    grouped = _coerce_plot_series(grouped, ["总入库金额", "总降本金额（负）", "降本百分比"])

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=grouped[level],
            y=grouped["总入库金额"],
            name="总入库金额",
            marker_color="#38bdf8",
            customdata=grouped[["总降本金额（负）", "降本百分比"]].values,
            hovertemplate=f"{level}=%{{x}}<br>总入库金额=%{{y:,.2f}}<br>总降本金额（负）=%{{customdata[0]:,.2f}}<br>降本百分比=%{{customdata[1]:.2%}}<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=grouped[level],
            y=grouped["总降本金额（负）"],
            name="总降本金额（负）",
            mode="lines+markers+text",
            line=dict(color="#22c55e", width=3),
            text=[f"{_format_short_money(v)}<br>{r:.2%}" if pd.notna(v) and pd.notna(r) else _format_short_money(v) for v, r in zip(grouped["总降本金额（负）"], grouped["降本百分比"])],
            textposition="top center",
            customdata=grouped[["总入库金额", "降本百分比"]].values,
            hovertemplate=f"{level}=%{{x}}<br>总降本金额（负）=%{{y:,.2f}}<br>总入库金额=%{{customdata[0]:,.2f}}<br>降本百分比=%{{customdata[1]:.2%}}<extra></extra>",
        ),
        secondary_y=True,
    )
    if len(grouped):
        receipt_max = float(grouped["总入库金额"].max()) if pd.notna(grouped["总入库金额"].max()) else 0.0
        reduction_max = float(grouped["总降本金额（负）"].max()) if pd.notna(grouped["总降本金额（负）"].max()) else 0.0
    else:
        receipt_max = 0.0
        reduction_max = 0.0
    fig.update_yaxes(title_text="总入库金额", secondary_y=False, tickformat=",.2f", range=[0, receipt_max * 1.18 if receipt_max > 0 else 1])
    fig.update_yaxes(title_text="总降本金额（负）", secondary_y=True, tickformat=",.2f", range=[0, reduction_max * 1.30 if reduction_max > 0 else 1])
    fig.update_xaxes(type="category")
    return _apply_layout(fig, f"{level}降本与入库概览", height=430)


def create_subcategory_top_chart(df: pd.DataFrame, top_n: int = 15) -> go.Figure:
    scoped = _ensure_metric_numeric(df)
    level_fields = [field for field in ["一级品类", "二级品类"] if field in scoped.columns]
    if len(level_fields) < 2:
        return _apply_layout(go.Figure(), "二级品类 Top 表现", height=430)

    grouped = aggregate_metrics(scoped, ["一级品类", "二级品类"]).rename(columns={"入库金额": "总入库金额"})
    grouped["一级品类"] = grouped["一级品类"].fillna("(空值)").astype(str)
    grouped["二级品类"] = grouped["二级品类"].fillna("(空值)").astype(str)
    grouped = grouped.sort_values(["总降本金额（负）", "总入库金额"], ascending=[False, False]).head(top_n).copy()
    grouped = _coerce_plot_series(grouped, ["总降本金额（负）", "总入库金额", "降本百分比"])
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=grouped["二级品类"],
            x=grouped["总降本金额（负）"],
            orientation="h",
            name="总降本金额（负）",
            marker=dict(
                color=grouped["降本百分比"],
                colorscale=[[0, "#38bdf8"], [0.5, "#22c55e"], [1, "#f59e0b"]],
                colorbar=dict(title="降本百分比", tickformat=".1%"),
            ),
            text=[f"入库 {_format_short_money(v)} | {r:.2%}" if pd.notna(v) and pd.notna(r) else f"入库 {_format_short_money(v)}" for v, r in zip(grouped["总入库金额"], grouped["降本百分比"])],
            textposition="outside",
            customdata=grouped[["二级品类", "一级品类", "总入库金额", "降本百分比"]].values,
            hovertemplate="二级品类=%{customdata[0]}<br>一级品类=%{customdata[1]}<br>总降本金额（负）=%{x:,.2f}<br>总入库金额=%{customdata[2]:,.2f}<br>降本百分比=%{customdata[3]:.2%}<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(tickformat=",.2f")
    return _apply_layout(fig, "二级品类 Top 降本表现", height=max(430, len(grouped) * 30))


def create_category_metric_bar(df: pd.DataFrame, level: str, metric_name: str = "总降本金额（负）", top_n: int = 12) -> go.Figure:
    scoped = _ensure_metric_numeric(df)
    grouped = aggregate_metrics(scoped, [level]).rename(columns={"入库金额": "总入库金额"})
    grouped[level] = grouped[level].fillna("(空值)").astype(str)
    grouped = grouped.sort_values(metric_name, ascending=False).head(top_n).copy()
    grouped = _coerce_plot_series(grouped, [metric_name, "总入库金额", "降本百分比"])
    fig = go.Figure(
        go.Bar(
            x=grouped[level],
            y=grouped[metric_name],
            marker=dict(
                color=grouped["降本百分比"],
                colorscale=[[0, "#38bdf8"], [0.5, "#22c55e"], [1, "#f59e0b"]],
                colorbar=dict(title="降本百分比", tickformat=".1%"),
            ),
            text=[
                f"{_format_short_money(v)}<br>{r:.2%}" if pd.notna(v) and pd.notna(r) else _format_short_money(v)
                for v, r in zip(grouped[metric_name], grouped["降本百分比"])
            ],
            textposition="outside",
            customdata=grouped[["总入库金额", "降本百分比"]].values,
            hovertemplate=f"{level}=%{{x}}<br>{metric_name}=%{{y:,.2f}}<br>总入库金额=%{{customdata[0]:,.2f}}<br>降本百分比=%{{customdata[1]:.2%}}<extra></extra>",
        )
    )
    fig = _apply_layout(fig, f"{level}{metric_name}对比", height=430)
    fig.update_xaxes(type="category")
    fig.update_yaxes(tickformat=",.2f")
    return fig


