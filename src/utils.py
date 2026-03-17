from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Optional, Tuple
from urllib.parse import parse_qs, urlparse
import logging
import math
import re

import numpy as np
import pandas as pd
import streamlit as st


LOGGER = logging.getLogger(__name__)


def setup_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


setup_logging()


def setup_page(page_title: str) -> None:
    st.set_page_config(
        page_title=page_title,
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def parse_feishu_sheet_url(url: str) -> Tuple[str, str]:
    parsed = urlparse(url.strip())
    match = re.search(r"/sheets/([A-Za-z0-9]+)", parsed.path)
    spreadsheet_token = match.group(1) if match else ""
    query = parse_qs(parsed.query)
    sheet_id = query.get("sheet", [""])[0]
    return spreadsheet_token, sheet_id


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == ""


def first_valid_header_row(rows: list[list[Any]], minimum_non_empty: int = 3) -> int:
    best_index = 0
    best_score = -1
    for idx, row in enumerate(rows):
        score = sum(0 if is_blank(cell) else 1 for cell in row)
        if score >= minimum_non_empty and score > best_score:
            best_score = score
            best_index = idx
    return best_index


EXCEL_EPOCH = datetime(1899, 12, 30)
TWO_PLACES = Decimal("0.01")


def parse_mixed_datetime(value: Any) -> pd.Timestamp:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return pd.NaT
    if isinstance(value, pd.Timestamp):
        return value
    text = str(value).strip()
    if not text:
        return pd.NaT
    if re.fullmatch(r"\d+(\.\d+)?", text):
        serial = float(text)
        if 1 <= serial <= 60000:
            return pd.Timestamp(EXCEL_EPOCH + timedelta(days=serial))
    parsed = pd.to_datetime(text, errors="coerce")
    return parsed if not pd.isna(parsed) else pd.NaT


def to_numeric_series(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace(r"\s+", "", regex=True)
        .replace({"": np.nan, "None": np.nan, "nan": np.nan})
    )
    return pd.to_numeric(cleaned, errors="coerce")


def quantize_2(value: Any) -> Optional[Decimal]:
    if value is None or pd.isna(value):
        return None
    try:
        return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return None


def round_series_2(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").round(2)


def safe_divide(numerator: Any, denominator: Any) -> Optional[float]:
    if denominator in (0, 0.0) or pd.isna(denominator):
        return None
    if pd.isna(numerator):
        return None
    return round(Decimal(str(numerator)) / Decimal(str(denominator)), 4)


def safe_divide_series(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace({0: np.nan})
    return numerator / denominator


def format_money(value: Any) -> str:
    if value is None or pd.isna(value):
        return "--"
    try:
        rounded = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return "--"
    return f"{int(rounded):,}"


def format_percent(value: Any) -> str:
    if value is None or pd.isna(value):
        return "--"
    quantized = quantize_2(Decimal(str(value)) * Decimal("100"))
    return "--" if quantized is None else f"{quantized:,.2f}%"


def format_count(value: Any) -> str:
    if value is None or pd.isna(value):
        return "--"
    return f"{int(round(float(value))):,}"


def format_date(value: Any) -> str:
    if value is None or pd.isna(value):
        return "--"
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def month_sort_key(label: str) -> tuple[int, int]:
    year, month = label.split("-")
    return int(year), int(month)


def option_label(value: Any) -> str:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return "(空值)"
    return str(value)


def coalesce_text(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()
