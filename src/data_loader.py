from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging

import pandas as pd
import streamlit as st

from .config import ConfigError, load_config
from .feishu_client import FeishuAPIError, FeishuClient
from .feishu_sheets import FeishuSheetsClient
from .transforms import clean_costdown_dataframe, normalize_dataframe_from_values


LOGGER = logging.getLogger(__name__)


@dataclass
class DataBundle:
    fact_df: pd.DataFrame
    date_dim: pd.DataFrame
    raw_df: pd.DataFrame
    error: str | None
    last_loaded_at: str | None



def _has_any_data(rows: list[list[object]]) -> bool:
    for row in rows:
        for cell in row:
            if cell is not None and str(cell).strip() != "":
                return True
    return False



def _read_chunk_with_retry(sheets: FeishuSheetsClient, sheet_id: str, start_row: int, end_row: int, end_column: str, min_chunk: int = 50) -> list[list[object]]:
    cell_range = f"A{start_row}:{end_column}{end_row}"
    try:
        return sheets.read_range(sheet_id, cell_range)
    except Exception:
        if end_row - start_row + 1 <= min_chunk:
            raise
        middle = (start_row + end_row) // 2
        left = _read_chunk_with_retry(sheets, sheet_id, start_row, middle, end_column, min_chunk=min_chunk)
        right = _read_chunk_with_retry(sheets, sheet_id, middle + 1, end_row, end_column, min_chunk=min_chunk)
        return left + right


@st.cache_data(ttl=600, show_spinner="正在从飞书读取数据...")
def load_raw_sheet_values() -> list[list[object]]:
    config = load_config()
    client = FeishuClient(config.app_id, config.app_secret, timeout=config.timeout)
    sheets = FeishuSheetsClient(client, config.spreadsheet_token)

    probe_range = f"A1:{config.end_column}{config.probe_rows}"
    probe_rows = sheets.read_range(config.sheet_id, probe_range)
    values = probe_rows.copy()

    start_row = config.probe_rows + 1
    empty_chunks = 0
    while start_row <= config.max_rows and empty_chunks < 2:
        end_row = min(start_row + config.chunk_size - 1, config.max_rows)
        chunk = _read_chunk_with_retry(sheets, config.sheet_id, start_row, end_row, config.end_column)
        if not _has_any_data(chunk):
            empty_chunks += 1
        else:
            empty_chunks = 0
            values.extend(chunk)
        start_row = end_row + 1
    return values


@st.cache_data(ttl=600, show_spinner="正在清洗数据...")
def get_clean_data_bundle() -> DataBundle:
    try:
        values = load_raw_sheet_values()
        raw_df = normalize_dataframe_from_values(values)
        fact_df, date_dim = clean_costdown_dataframe(raw_df)
        return DataBundle(
            fact_df=fact_df,
            date_dim=date_dim,
            raw_df=raw_df,
            error=None,
            last_loaded_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    except (ConfigError, FeishuAPIError, RuntimeError, ValueError) as exc:
        LOGGER.exception("Load data failed")
        empty = pd.DataFrame()
        return DataBundle(
            fact_df=empty,
            date_dim=empty,
            raw_df=empty,
            error=str(exc),
            last_loaded_at=None,
        )
