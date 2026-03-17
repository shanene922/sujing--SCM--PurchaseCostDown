from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from .date_dim import build_date_dim
from .utils import coalesce_text, first_valid_header_row, option_label, parse_mixed_datetime, round_series_2, safe_divide_series, to_numeric_series


NUMERIC_COLUMNS = [
    "降本金额",
    "入库金额",
    "入库数量",
    "价税合计",
    "含税单价",
    "订货数量",
    "入库不含税金额",
    "入库含税单价",
    "25年采购含税均价",
    "月份",
]

STRING_COLUMNS = [
    "采购组织",
    "采购员",
    "SOURCING",
    "订单编号",
    "供应商编码",
    "供应商名称",
    "物料编码",
    "物料名称",
    "规格型号",
    "ECN\\NPI\\旧料号",
    "旧物料号",
    "存货类别",
    "物料属性",
    "物料分组",
    "降本类别",
]

DATE_COLUMNS = ["日期", "2026年首次采购日期"]
FILL_DOWN_COLUMNS = ["采购组织", "采购员", "订单编号", "供应商编码", "供应商名称"]



def normalize_dataframe_from_values(values: List[List[object]]) -> pd.DataFrame:
    if not values:
        return pd.DataFrame()
    header_index = first_valid_header_row(values)
    header = values[header_index]
    columns = []
    for idx, cell in enumerate(header):
        name = coalesce_text(cell)
        columns.append(name if name else f"Unnamed_{idx}")

    rows = values[header_index + 1 :]
    normalized_rows = []
    for row in rows:
        row = list(row or [])
        if len(row) < len(columns):
            row.extend([None] * (len(columns) - len(row)))
        normalized_rows.append(row[: len(columns)])
    return pd.DataFrame(normalized_rows, columns=columns)



def clean_costdown_dataframe(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if raw_df.empty:
        return raw_df, build_date_dim(None, None)

    df = raw_df.copy()
    df.columns = [str(col).strip().replace("\n", "") for col in df.columns]
    df = df.replace(r"^\s*$", np.nan, regex=True)
    df = df.dropna(how="all").reset_index(drop=True)

    for col in FILL_DOWN_COLUMNS:
        if col in df.columns:
            df[col] = df[col].ffill()

    for col in STRING_COLUMNS:
        if col in df.columns:
            df[col] = df[col].map(option_label)

    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = to_numeric_series(df[col])

    for col in DATE_COLUMNS:
        if col in df.columns:
            df[col] = df[col].map(parse_mixed_datetime)

    if "月份" not in df.columns:
        df["月份"] = np.nan
    if "日期" in df.columns:
        derived_month = df["日期"].dt.month
        df["月份"] = df["月份"].fillna(derived_month)

    if "降本金额" not in df.columns:
        df["降本金额"] = 0.0
    if "入库数量" not in df.columns:
        df["入库数量"] = 0.0
    if "入库金额" not in df.columns:
        df["入库金额"] = 0.0

    df["总降本"] = df["降本金额"].fillna(0) * df["入库数量"].fillna(0)
    df["总降本金额（负）"] = -df["总降本"]
    df["行降本百分比"] = safe_divide_series(-df["总降本"], df["入库金额"])
    for col in ["降本金额", "入库金额", "入库数量", "总降本", "总降本金额（负）", "行降本百分比", "25年采购含税均价", "入库含税单价", "含税单价", "价税合计", "入库不含税金额"]:
        if col in df.columns:
            df[col] = round_series_2(df[col])

    date_dim = build_date_dim(df["日期"].min() if "日期" in df.columns else None, df["日期"].max() if "日期" in df.columns else None)

    if "日期" in df.columns:
        df["Date"] = pd.to_datetime(df["日期"]).dt.normalize()
        df = df.merge(date_dim, how="left", on="Date")
    else:
        df["Date"] = pd.NaT
        for col in ["Year", "MonthNo", "Month", "Quarter", "Day", "WeekdayNo", "Weekday", "WeekNo", "WeekKey"]:
            df[col] = np.nan

    df["Year"] = df["Year"].astype("Int64")
    df["MonthNo"] = df["MonthNo"].astype("Int64")
    df["WeekNo"] = df["WeekNo"].astype("Int64")
    df["月份"] = pd.to_numeric(df["月份"], errors="coerce").astype("Int64")

    ordered_columns = list(dict.fromkeys(df.columns.tolist()))
    df = df[ordered_columns]
    return df, date_dim
