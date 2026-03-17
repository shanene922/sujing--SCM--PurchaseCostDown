from __future__ import annotations

CSS = """
<style>
:root {
    --bg: #0b1220;
    --panel: #121b2b;
    --panel-2: #17243a;
    --border: rgba(148, 163, 184, 0.15);
    --text: #e5eefb;
    --muted: #8aa0bf;
    --accent: #38bdf8;
    --accent-2: #22c55e;
    --warn: #f97316;
    --danger: #fb7185;
}
html, body, [class*="css"]  {
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
}
.stApp {
    background:
        radial-gradient(circle at top left, rgba(56, 189, 248, 0.08), transparent 20%),
        radial-gradient(circle at top right, rgba(34, 197, 94, 0.06), transparent 18%),
        var(--bg);
    color: var(--text);
}
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(18,27,43,0.98), rgba(11,18,32,0.98));
    border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] .block-container {
    padding-top: 1.2rem;
}
.block-container {
    padding-top: 5.2rem;
    padding-bottom: 2rem;
}
.page-title {
    font-size: 2.2rem;
    font-weight: 800;
    color: #dbeafe;
    margin-bottom: 0.35rem;
}
.page-subtitle {
    color: var(--muted);
    margin-bottom: 1.2rem;
}
.hero-card, .metric-card, .chart-card, .table-card, .info-card {
    background: linear-gradient(180deg, rgba(18,27,43,0.94), rgba(11,18,32,0.96));
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: 0 16px 36px rgba(0, 0, 0, 0.22);
}
.hero-card, .metric-card {
    padding: 1rem 1.1rem;
    min-height: 118px;
}
.hero-label, .metric-label {
    color: var(--muted);
    font-size: 0.9rem;
    margin-bottom: 0.55rem;
}
.hero-value, .metric-value {
    color: var(--text);
    font-size: 1.8rem;
    font-weight: 800;
    line-height: 1.1;
}
.metric-delta {
    margin-top: 0.65rem;
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.22rem 0.6rem;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 700;
}
.metric-delta.up {
    background: rgba(34, 197, 94, 0.16);
    color: #86efac;
}
.metric-delta.down {
    background: rgba(251, 113, 133, 0.16);
    color: #fda4af;
}
.metric-delta.flat {
    background: rgba(148, 163, 184, 0.16);
    color: #cbd5e1;
}
.section-title {
    color: #93c5fd;
    font-size: 1.2rem;
    font-weight: 800;
    margin: 0.5rem 0 0.8rem;
}
.card-title {
    color: #dbeafe;
    font-size: 1rem;
    font-weight: 700;
    margin-bottom: 0.7rem;
}
.card-caption {
    color: var(--muted);
    font-size: 0.86rem;
    margin-bottom: 0.9rem;
}
.stContainer[data-testid="stVerticalBlock"] > div:has(> .filter-box) {
    margin-bottom: 0.85rem;
}
.filter-box {
    background: rgba(23, 36, 58, 0.72);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 0.75rem 0.8rem 0.2rem;
}
.filter-title {
    color: #cfe6ff;
    font-size: 0.88rem;
    font-weight: 700;
    margin-bottom: 0.35rem;
}
.stMultiSelect > div > div,
.stSelectbox > div > div,
.stTextInput > div > div,
.stDateInput > div > div {
    background: rgba(11, 18, 32, 0.95);
    color: var(--text);
    border-radius: 12px;
}
.stButton > button {
    background: rgba(23, 36, 58, 0.95);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 10px;
}
.stButton > button:hover {
    border-color: rgba(56, 189, 248, 0.6);
    color: white;
}
.ag-theme-streamlit {
    --ag-background-color: #0f172a;
    --ag-foreground-color: #e2e8f0;
    --ag-border-color: rgba(148, 163, 184, 0.15);
    --ag-header-background-color: #162033;
    --ag-row-hover-color: rgba(56, 189, 248, 0.08);
    --ag-odd-row-background-color: rgba(255, 255, 255, 0.01);
}
.ag-theme-streamlit .ag-center-header .ag-header-group-cell-label {
    justify-content: center !important;
    text-align: center !important;
}
</style>
"""


def apply_global_styles() -> None:
    import streamlit as st

    st.markdown(CSS, unsafe_allow_html=True)
