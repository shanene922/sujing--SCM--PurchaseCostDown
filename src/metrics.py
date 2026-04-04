from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional

import numpy as np
import pandas as pd

from .utils import safe_divide


MetricFunc = Callable[[pd.DataFrame], Optional[float]]


@dataclass
class MetricSnapshot:
    total_costdown_amount: float
    total_costdown_amount_negative: float
    total_receipt_amount: float
    costdown_ratio: Optional[float]
    supplier_up_amount: float
    supplier_down_amount: float
    supplier_up_ratio: Optional[float]
    supplier_down_ratio: Optional[float]
    po_count: int
    material_count: int
    supplier_count: int
    cutoff_date: pd.Timestamp | None
    discount_material_count: int
    increase_material_count: int
    discount_supplier_count: int
    increase_supplier_count: int
    weighted_avg_receipt_price: Optional[float]



def _sum(df: pd.DataFrame, col: str) -> float:
    return round(df[col].fillna(0).sum(), 2) if col in df.columns else 0.0



def _category_scope(df: pd.DataFrame, category: str) -> pd.DataFrame:
    if "降本类别" not in df.columns:
        return df.iloc[0:0]
    return df[df["降本类别"] == category]



def total_costdown_amount(df: pd.DataFrame) -> float:
    return _sum(df, "总降本")



def total_costdown_amount_negative(df: pd.DataFrame) -> float:
    return -total_costdown_amount(df)



def total_receipt_amount(df: pd.DataFrame) -> float:
    return _sum(df, "入库金额")



def costdown_ratio(df: pd.DataFrame) -> Optional[float]:
    return safe_divide(total_costdown_amount_negative(df), total_receipt_amount(df))



def total_receipt_amount_ytd(df: pd.DataFrame) -> float:
    return total_receipt_amount(_get_ytd_df(df))



def total_costdown_amount_ytd(df: pd.DataFrame) -> float:
    return total_costdown_amount(_get_ytd_df(df))



def costdown_ratio_ytd(df: pd.DataFrame) -> Optional[float]:
    return costdown_ratio(_get_ytd_df(df))



def total_receipt_amount_mtd(df: pd.DataFrame) -> float:
    return total_receipt_amount(_get_mtd_df(df))



def total_costdown_amount_mtd(df: pd.DataFrame) -> float:
    return total_costdown_amount(_get_mtd_df(df))



def costdown_ratio_mtd(df: pd.DataFrame) -> Optional[float]:
    return costdown_ratio(_get_mtd_df(df))



def supplier_up_amount(df: pd.DataFrame) -> float:
    return total_costdown_amount(_category_scope(df, "涨价"))



def supplier_down_amount(df: pd.DataFrame) -> float:
    return total_costdown_amount(_category_scope(df, "降价"))



def supply_chain_down_amount_negative(df: pd.DataFrame) -> float:
    return -supplier_down_amount(df)



def supplier_up_ratio(df: pd.DataFrame) -> Optional[float]:
    return safe_divide(supplier_up_amount(df), total_receipt_amount(df))



def supplier_down_ratio(df: pd.DataFrame) -> Optional[float]:
    return safe_divide(supplier_down_amount(df), total_receipt_amount(df))



def po_count(df: pd.DataFrame) -> int:
    return int(df["订单编号"].dropna().nunique()) if "订单编号" in df.columns else 0



def material_count(df: pd.DataFrame) -> int:
    return int(df["物料编码"].dropna().nunique()) if "物料编码" in df.columns else 0



def supplier_count(df: pd.DataFrame) -> int:
    if "供应商编码" in df.columns:
        codes = df["供应商编码"].dropna().astype(str).str.strip()
        codes = codes[codes.ne("")]
        if not codes.empty:
            return int(codes.nunique())
    if "供应商名称" in df.columns:
        names = df["供应商名称"].dropna().astype(str).str.strip()
        names = names[names.ne("")]
        return int(names.nunique())
    return 0



def cutoff_date(df: pd.DataFrame) -> Optional[pd.Timestamp]:
    if "日期" not in df.columns or df.empty:
        return None
    value = df["日期"].max()
    return None if pd.isna(value) else pd.Timestamp(value)



def discount_material_count(df: pd.DataFrame) -> int:
    scoped = _category_scope(df, "降价")
    return int(scoped["物料编码"].dropna().nunique()) if "物料编码" in scoped.columns else 0



def increase_material_count(df: pd.DataFrame) -> int:
    scoped = _category_scope(df, "涨价")
    return int(scoped["物料编码"].dropna().nunique()) if "物料编码" in scoped.columns else 0



def discount_supplier_count(df: pd.DataFrame) -> int:
    scoped = _category_scope(df, "降价")
    return int(scoped["供应商名称"].dropna().nunique()) if "供应商名称" in scoped.columns else 0



def increase_supplier_count(df: pd.DataFrame) -> int:
    scoped = _category_scope(df, "涨价")
    return int(scoped["供应商名称"].dropna().nunique()) if "供应商名称" in scoped.columns else 0



def weighted_avg_receipt_price(df: pd.DataFrame) -> Optional[float]:
    return safe_divide(total_receipt_amount(df), _sum(df, "入库数量"))


METRIC_MAP: Dict[str, MetricFunc] = {
    "总降本金额": total_costdown_amount,
    "总降本金额（负）": total_costdown_amount_negative,
    "总入库金额": total_receipt_amount,
    "降本百分比": costdown_ratio,
    "总降本金额 YTD": total_costdown_amount_ytd,
    "总入库金额 YTD": total_receipt_amount_ytd,
    "降本百分比 YTD": costdown_ratio_ytd,
    "总入库金额 MTD": total_receipt_amount_mtd,
    "总降本金额 MTD": total_costdown_amount_mtd,
    "降本百分比 MTD": costdown_ratio_mtd,
    "供应商涨价金额": supplier_up_amount,
    "供应商降价金额": supplier_down_amount,
    "供应链降价金额（负）": supply_chain_down_amount_negative,
    "供应商涨价比例": supplier_up_ratio,
    "供应商降价比例": supplier_down_ratio,
    "PO总数": po_count,
    "物料编码数": material_count,
    "供应商数量": supplier_count,
    "降价物料数": discount_material_count,
    "涨价物料数": increase_material_count,
    "降价供应商数": discount_supplier_count,
    "涨价供应商数": increase_supplier_count,
    "加权平均入库价格": weighted_avg_receipt_price,
}



def _get_ytd_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "日期" not in df.columns:
        return df
    max_date = pd.Timestamp(df["日期"].max())
    return df[(df["日期"].dt.year == max_date.year) & (df["日期"] <= max_date)]



def _get_mtd_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "日期" not in df.columns:
        return df
    max_date = pd.Timestamp(df["日期"].max())
    return df[
        (df["日期"].dt.year == max_date.year)
        & (df["日期"].dt.month == max_date.month)
        & (df["日期"] <= max_date)
    ]



def get_metric_value(metric_name: str, df: pd.DataFrame) -> Optional[float]:
    return METRIC_MAP[metric_name](df)



def compute_mom_delta(metric_name: str, current_df: pd.DataFrame, comparison_df: pd.DataFrame) -> Optional[float]:
    if current_df.empty or "Month" not in current_df.columns or current_df["Month"].dropna().empty:
        return None

    latest_month = sorted(current_df["Month"].dropna().unique())[-1]
    latest_period = current_df[current_df["Month"] == latest_month]
    current_value = get_metric_value(metric_name, latest_period)

    if comparison_df.empty or "日期" not in comparison_df.columns or comparison_df["日期"].dropna().empty:
        return None
    previous_period_key = pd.Period(latest_month, freq="M") - 1
    previous_df = comparison_df[pd.to_datetime(comparison_df["日期"]).dt.to_period("M") == previous_period_key]
    previous_value = get_metric_value(metric_name, previous_df)

    if previous_value in (None, 0) or pd.isna(previous_value):
        return None
    return safe_divide(current_value - previous_value, previous_value)



def get_kpi_snapshot(df: pd.DataFrame, comparison_df: pd.DataFrame | None = None) -> MetricSnapshot:
    return MetricSnapshot(
        total_costdown_amount=total_costdown_amount(df),
        total_costdown_amount_negative=total_costdown_amount_negative(df),
        total_receipt_amount=total_receipt_amount(df),
        costdown_ratio=costdown_ratio(df),
        supplier_up_amount=supplier_up_amount(df),
        supplier_down_amount=supplier_down_amount(df),
        supplier_up_ratio=supplier_up_ratio(df),
        supplier_down_ratio=supplier_down_ratio(df),
        po_count=po_count(df),
        material_count=material_count(df),
        supplier_count=supplier_count(df),
        cutoff_date=cutoff_date(df),
        discount_material_count=discount_material_count(df),
        increase_material_count=increase_material_count(df),
        discount_supplier_count=discount_supplier_count(df),
        increase_supplier_count=increase_supplier_count(df),
        weighted_avg_receipt_price=weighted_avg_receipt_price(df),
    )



def aggregate_metrics(df: pd.DataFrame, group_fields: list[str]) -> pd.DataFrame:
    grouped = (
        df.groupby(group_fields, dropna=False)
        .agg(
            总降本=("总降本", "sum"),
            入库金额=("入库金额", "sum"),
            入库数量=("入库数量", "sum"),
        )
        .reset_index()
    )
    grouped["总降本"] = pd.to_numeric(grouped["总降本"], errors="coerce")
    grouped["入库金额"] = pd.to_numeric(grouped["入库金额"], errors="coerce")
    grouped["入库数量"] = pd.to_numeric(grouped["入库数量"], errors="coerce")
    grouped["总降本金额（负）"] = -grouped["总降本"]
    grouped["降本百分比"] = grouped["总降本金额（负）"] / grouped["入库金额"].replace({0: np.nan})
    grouped["加权平均入库价格"] = grouped["入库金额"] / grouped["入库数量"].replace({0: np.nan})
    return grouped
