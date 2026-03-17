from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

import pandas as pd
import streamlit as st

from .state import clear_chart_selections, ensure_session_state
from .utils import option_label


FILTER_FIELDS = ["SOURCING", "供应商名称", "Year", "Quarter", "Month", "物料名称", "降本类别"]
TIME_FIELDS = {"Year", "Quarter", "Month"}
NON_TIME_FIELDS = ["SOURCING", "供应商名称", "物料名称", "降本类别"]



def _series_options(df: pd.DataFrame, field: str) -> list[Any]:
    if field not in df.columns:
        return []
    series = df[field].dropna()
    options = sorted(series.unique().tolist())
    if field == "Month":
        options = sorted(options)
    if field == "Quarter":
        options = sorted(options, key=lambda x: str(x))
    return options



def sanitize_filters(df: pd.DataFrame) -> None:
    ensure_session_state()
    base = st.session_state.global_filters

    source_df = df.copy()
    for field in NON_TIME_FIELDS:
        options = _series_options(source_df, field)
        selected = base.get(field) or options
        base[field] = [value for value in selected if value in options] or options
        if base[field]:
            source_df = source_df[source_df[field].isin(base[field])]

    year_options = _series_options(source_df, "Year")
    year_selected = base.get("Year") or year_options
    base["Year"] = [value for value in year_selected if value in year_options] or year_options
    year_df = source_df if not base["Year"] else source_df[source_df["Year"].isin(base["Year"])]

    quarter_options = _series_options(year_df, "Quarter")
    quarter_selected = base.get("Quarter") or quarter_options
    base["Quarter"] = [value for value in quarter_selected if value in quarter_options] or quarter_options
    quarter_df = year_df if not base["Quarter"] else year_df[year_df["Quarter"].isin(base["Quarter"])]

    month_options = _series_options(quarter_df, "Month")
    month_selected = base.get("Month") or month_options
    base["Month"] = [value for value in month_selected if value in month_options] or month_options



def apply_global_filters(
    df: pd.DataFrame,
    filters: Dict[str, list[Any]],
    *,
    exclude_fields: Optional[set[str]] = None,
) -> pd.DataFrame:
    if df.empty:
        return df
    exclude_fields = exclude_fields or set()
    filtered = df.copy()
    for field, values in filters.items():
        if field in exclude_fields or field not in filtered.columns:
            continue
        if values:
            filtered = filtered[filtered[field].isin(values)]
    return filtered



def apply_chart_selections(df: pd.DataFrame, selections: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    scoped = df.copy()
    for selection in selections.values():
        field = selection.get("field")
        value = selection.get("value")
        if field == "WeekKey" and "WeekKey" in scoped.columns:
            scoped = scoped[scoped["WeekKey"] == value]
        elif field == "Date" and "Date" in scoped.columns:
            scoped = scoped[scoped["Date"].astype(str) == str(value)]
        elif field in scoped.columns:
            scoped = scoped[scoped[field].astype(str) == str(value)]
    return scoped



def _render_multiselect(field: str, options: list[Any], label: str) -> None:
    key = f"widget_{field}"
    current = st.session_state.global_filters.get(field, options) or options
    safe_current = [value for value in current if value in options] or options

    st.markdown("<div class='filter-box'>", unsafe_allow_html=True)
    st.markdown(f"<div class='filter-title'>{label}</div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("全选", key=f"select_all_{field}", use_container_width=True):
            st.session_state.global_filters[field] = options
            st.session_state[key] = options
            st.rerun()
    with col2:
        if st.button("清空", key=f"clear_{field}", use_container_width=True):
            st.session_state.global_filters[field] = []
            st.session_state[key] = []
            st.rerun()
    selected = st.multiselect(
        label,
        options=options,
        default=safe_current,
        key=key,
        label_visibility="collapsed",
        placeholder="搜索或选择",
    )
    st.session_state.global_filters[field] = selected or options
    st.markdown("</div>", unsafe_allow_html=True)



def render_global_sidebar(bundle: Any) -> None:
    ensure_session_state()
    with st.sidebar:
        st.markdown("## 全局筛选")
        if st.button("刷新数据", use_container_width=True, type="primary"):
            st.cache_data.clear()
            clear_chart_selections()
            st.rerun()

        if bundle.error:
            st.error(bundle.error)
            return

        df = bundle.fact_df
        sanitize_filters(df)
        filter_labels = {
            "SOURCING": "SOURCING",
            "供应商名称": "供应商名称",
            "Year": "Year",
            "Quarter": "Quarter",
            "Month": "Month",
            "物料名称": "物料名称",
            "降本类别": "降本类别",
        }

        non_time_df = df.copy()
        for field in NON_TIME_FIELDS:
            options = _series_options(non_time_df, field)
            _render_multiselect(field, options, filter_labels[field])
            selected = st.session_state.global_filters[field]
            if selected:
                non_time_df = non_time_df[non_time_df[field].isin(selected)]

        year_options = _series_options(non_time_df, "Year")
        _render_multiselect("Year", year_options, "Year")
        year_df = non_time_df if not st.session_state.global_filters["Year"] else non_time_df[non_time_df["Year"].isin(st.session_state.global_filters["Year"])]

        quarter_options = _series_options(year_df, "Quarter")
        _render_multiselect("Quarter", quarter_options, "Quarter")
        quarter_df = year_df if not st.session_state.global_filters["Quarter"] else year_df[year_df["Quarter"].isin(st.session_state.global_filters["Quarter"])]

        month_options = _series_options(quarter_df, "Month")
        _render_multiselect("Month", month_options, "Month")

        st.caption(f"数据行数：{len(df):,}")
        if bundle.last_loaded_at:
            st.caption(f"最近加载：{bundle.last_loaded_at}")
