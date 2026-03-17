from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

import streamlit as st


GLOBAL_FILTER_DEFAULTS = {
    "SOURCING": [],
    "供应商名称": [],
    "Year": [],
    "Quarter": [],
    "Month": [],
    "物料名称": [],
    "降本类别": [],
}


@dataclass
class ChartSelection:
    field: str
    value: Any
    label: str



def ensure_session_state() -> None:
    if "global_filters" not in st.session_state:
        st.session_state.global_filters = GLOBAL_FILTER_DEFAULTS.copy()
    if "chart_selections" not in st.session_state:
        st.session_state.chart_selections = {}



def clear_chart_selections(prefix: Optional[str] = None) -> None:
    ensure_session_state()
    if prefix is None:
        st.session_state.chart_selections = {}
        return
    st.session_state.chart_selections = {
        key: value
        for key, value in st.session_state.chart_selections.items()
        if not key.startswith(prefix)
    }



def toggle_chart_selection(key: str, selection: Optional[Dict[str, Any]]) -> None:
    ensure_session_state()
    if not selection:
        return
    current = st.session_state.chart_selections.get(key)
    if current == selection:
        st.session_state.chart_selections.pop(key, None)
    else:
        st.session_state.chart_selections[key] = selection



def get_page_chart_selections(prefix: str) -> Dict[str, Dict[str, Any]]:
    ensure_session_state()
    return {
        key: value
        for key, value in st.session_state.chart_selections.items()
        if key.startswith(prefix)
    }
