from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from urllib.parse import parse_qs, urlparse
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from .feishu_client import FeishuClient


DEFAULT_BOM_PATH = Path(r"D:\Users\Speediance\Desktop\测试\最新版本BOM.xlsx")
DEFAULT_MATERIAL_MASTER_PATH = Path(r"D:\Users\Speediance\Desktop\测试\物料清单.xlsx")
DEFAULT_PURCHASE_COSTDOWN_PATH = Path(r"D:\Users\Speediance\Desktop\测试\output\Purchase\purchase_costdown_20260401.xlsx")
DEFAULT_TARGETS = ["99.01.00116", "21.01.00245", "21.01.00245-A1", "21.01.00288", "21.01.00333"]
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ENV_PATH)


@dataclass
class MachineCostdownBundle:
    summary_df: pd.DataFrame
    time_df: pd.DataFrame
    detail_df: pd.DataFrame
    unpriced_df: pd.DataFrame
    error: str | None
    source_info: dict[str, str]


def _parse_bitable_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query)
    table_id = (query.get("table") or [""])[0]
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    app_token = ""
    for idx in range(len(parts) - 1):
        if parts[idx] == "base":
            app_token = parts[idx + 1]
            break
    if not app_token or not table_id:
        raise ValueError("Cost_Table 无法解析 app_token/table_id，请使用 /base/<app_token>?table=<table_id> 形式。")
    return app_token, table_id


def _normalize_bitable_field_name(name: str) -> str:
    return str(name or "").replace(" ", "").replace("\n", "").strip().lower()


def _pick_existing_field(columns: list[str], candidates: list[str]) -> str:
    normalized_map = {_normalize_bitable_field_name(col): col for col in columns}
    for candidate in candidates:
        found = normalized_map.get(_normalize_bitable_field_name(candidate))
        if found:
            return found
    raise KeyError(f"未找到字段，候选={candidates}，现有字段={columns}")


def _parse_mixed_datetime(value) -> pd.Timestamp:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return pd.NaT
    if isinstance(value, pd.Timestamp):
        return value
    text = str(value).strip()
    if not text:
        return pd.NaT
    if text.isdigit():
        number = int(text)
        if number >= 1_000_000_000_000:
            return pd.to_datetime(number, unit="ms", errors="coerce")
        if number >= 1_000_000_000:
            return pd.to_datetime(number, unit="s", errors="coerce")
    return pd.to_datetime(text, errors="coerce")


def _list_bitable_records(client: FeishuClient, app_token: str, table_id: str, page_size: int = 500) -> list[dict]:
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    page_token = None
    records: list[dict] = []
    while True:
        params = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        payload = client.request("GET", url, params=params)
        data = payload.get("data") or {}
        records.extend(data.get("items") or [])
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
    return records


def _load_cost_table_from_bitable(url: str) -> pd.DataFrame:
    app_id = (os.getenv("APP_ID") or os.getenv("FEISHU_APP_ID") or "").strip()
    app_secret = (os.getenv("APP_SECRET") or os.getenv("FEISHU_APP_SECRET") or "").strip()
    if not app_id or not app_secret:
        raise RuntimeError(f"缺少 APP_ID/APP_SECRET，请检查 {ENV_PATH}")
    app_token, table_id = _parse_bitable_url(url)
    client = FeishuClient(app_id, app_secret, timeout=int((os.getenv("FEISHU_TIMEOUT") or "30").strip() or 30))
    records = _list_bitable_records(client, app_token, table_id)
    rows = [record.get("fields") or {} for record in records]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df.columns = [str(col).strip() for col in df.columns]
    material_code_col = _pick_existing_field(df.columns.tolist(), ["物料编码", "编码", "料号"])
    price_col = _pick_existing_field(df.columns.tolist(), ["含税单价"])
    effective_col = _pick_existing_field(df.columns.tolist(), ["生效日期", "价格生效日期"])
    result = pd.DataFrame(
        {
            "物料编码": df[material_code_col].map(lambda x: str(x).strip() if x is not None else ""),
            "含税单价": pd.to_numeric(df[price_col], errors="coerce"),
            "生效日期": df[effective_col].map(_parse_mixed_datetime),
        }
    )
    result = result[result["物料编码"].ne("") & result["含税单价"].notna() & result["生效日期"].notna()].copy()
    result = result.sort_values(["物料编码", "生效日期"]).reset_index(drop=True)
    return result


def _import_rollup_helpers():
    from scripts.purchase_material_cost_rollup import (
        build_bom_graph,
        load_material_master,
        normalize_text,
        preprocess_bom,
        q5,
        read_bom_sheet,
    )

    return build_bom_graph, load_material_master, normalize_text, preprocess_bom, q5, read_bom_sheet


def _load_purchase_costdown_enriched(xlsx_path: Path):
    _, _, normalize_text, _, _, _ = _import_rollup_helpers()
    df = pd.read_excel(xlsx_path, dtype="object")
    df.columns = [normalize_text(c) for c in df.columns]
    for col in ["物料编码", "物料名称", "供应商名称", "SOURCING", "降本类别"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].map(normalize_text)
    for col in ["入库数量", "入库金额", "入库含税单价", "降本金额"]:
        if col not in df.columns:
            df[col] = pd.NA
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["总降本"] = df["降本金额"] * df["入库数量"]
    df["入库日期_dt"] = pd.to_datetime(df.get("入库日期"), errors="coerce")
    return df


def _dominant_label_by_amount(df: pd.DataFrame, key_col: str, value_col: str) -> pd.Series:
    if df.empty or key_col not in df.columns:
        return pd.Series(dtype="object")
    scoped = df[df[key_col].astype(str).str.strip().ne("")].copy()
    if scoped.empty:
        return pd.Series(dtype="object")
    grouped = scoped.groupby(["物料编码", key_col], dropna=False)[value_col].sum().reset_index()
    grouped = grouped.sort_values(["物料编码", value_col], ascending=[True, False])
    return grouped.drop_duplicates("物料编码").set_index("物料编码")[key_col]


def _summarize_purchase_for_dashboard(df: pd.DataFrame) -> pd.DataFrame:
    valid = df[df["物料编码"].ne("") & df["入库数量"].notna() & (df["入库数量"] > 0) & df["入库金额"].notna()].copy()
    if valid.empty:
        return pd.DataFrame()

    grouped = (
        valid.groupby("物料编码", dropna=False)
        .agg(
            物料名称=("物料名称", "first"),
            **{
                "2026采购数量": ("入库数量", "sum"),
                "2026采购金额": ("入库金额", "sum"),
                "2026总降本": ("总降本", "sum"),
                "最近入库日期": ("入库日期_dt", "max"),
            },
        )
        .reset_index()
    )
    grouped["2026加权采购单价"] = grouped["2026采购金额"] / grouped["2026采购数量"].replace({0: pd.NA})
    grouped["2026加权降本单价"] = grouped["2026总降本"] / grouped["2026采购数量"].replace({0: pd.NA})

    up = valid[valid["降本类别"] == "涨价"].groupby("物料编码")["总降本"].sum()
    down = valid[valid["降本类别"] == "降价"].groupby("物料编码")["总降本"].sum()
    grouped["2026涨价金额"] = grouped["物料编码"].map(up).fillna(0.0)
    grouped["2026降价金额（负）"] = -grouped["物料编码"].map(down).fillna(0.0)
    grouped["2026总降本金额（负）"] = -grouped["2026总降本"]
    grouped["最近入库日期"] = grouped["最近入库日期"].dt.strftime("%Y-%m-%d").fillna("")

    dominant_supplier = _dominant_label_by_amount(valid, "供应商名称", "入库金额")
    dominant_sourcing = _dominant_label_by_amount(valid, "SOURCING", "入库金额")
    grouped["主供应商"] = grouped["物料编码"].map(dominant_supplier).fillna("")
    grouped["主SOURCING"] = grouped["物料编码"].map(dominant_sourcing).fillna("")
    return grouped


def _summarize_purchase_for_dashboard_by_month(df: pd.DataFrame) -> pd.DataFrame:
    valid = df[df["物料编码"].ne("") & df["入库数量"].notna() & (df["入库数量"] > 0) & df["入库金额"].notna() & df["入库日期_dt"].notna()].copy()
    if valid.empty:
        return pd.DataFrame()

    valid["Month"] = valid["入库日期_dt"].dt.strftime("%Y-%m")
    valid["Year"] = valid["入库日期_dt"].dt.year.astype("Int64")
    valid["MonthNo"] = valid["入库日期_dt"].dt.month.astype("Int64")

    grouped = (
        valid.groupby(["物料编码", "Month", "Year", "MonthNo"], dropna=False)
        .agg(
            物料名称=("物料名称", "first"),
            **{
                "2026采购数量": ("入库数量", "sum"),
                "2026采购金额": ("入库金额", "sum"),
                "2026总降本": ("总降本", "sum"),
            },
        )
        .reset_index()
    )
    grouped["2026加权采购单价"] = grouped["2026采购金额"] / grouped["2026采购数量"].replace({0: pd.NA})
    grouped["2026加权降本单价"] = grouped["2026总降本"] / grouped["2026采购数量"].replace({0: pd.NA})
    grouped["2026总降本金额（负）"] = -grouped["2026总降本"]
    return grouped


def _rollup_machine_dashboard(
    targets: List[str],
    graph: Dict[str, List[object]],
    bom_name_map: Dict[str, str],
    material_df: pd.DataFrame,
    purchase_summary: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    _, _, normalize_text, _, q5, _ = _import_rollup_helpers()
    material_map = material_df.set_index("编码").to_dict(orient="index")
    purchase_map = purchase_summary.set_index("物料编码").to_dict(orient="index")
    purchased_codes = set(purchase_summary["物料编码"].tolist())

    detail_rows: list[dict] = []
    unpriced_rows: list[dict] = []

    for target in targets:
        target = normalize_text(target)
        target_meta = material_map.get(target, {})
        product_line = normalize_text(target_meta.get("产品线", ""))
        root_name = normalize_text(target_meta.get("名称", "")) or bom_name_map.get(target, "")
        stack: list[tuple[str, float, int, list[str]]] = [(target, 1.0, 0, [target])]

        while stack:
            parent, parent_acc, level, path = stack.pop()
            for edge in graph.get(parent, []):
                child = edge.child_code
                if child in path:
                    continue

                acc_qty = parent_acc * float(q5(edge.single_qty))
                current_path = path + [child]
                if child in purchased_codes:
                    purchase_meta = purchase_map.get(child, {})
                    unit_price = pd.to_numeric(purchase_meta.get("2026加权采购单价"), errors="coerce")
                    delta_unit = pd.to_numeric(purchase_meta.get("2026加权降本单价"), errors="coerce")
                    detail_rows.append(
                        {
                            "产品线": product_line,
                            "整机物料编码": target,
                            "整机物料名称": root_name,
                            "采购层级物料编码": child,
                            "采购层级物料名称": normalize_text(purchase_meta.get("物料名称", "")) or edge.child_name,
                            "主供应商": normalize_text(purchase_meta.get("主供应商", "")),
                            "主SOURCING": normalize_text(purchase_meta.get("主SOURCING", "")),
                            "BOM层级": level + 1,
                            "路径": " -> ".join(current_path),
                            "累计用量": round(acc_qty, 5),
                            "2026采购数量": pd.to_numeric(purchase_meta.get("2026采购数量"), errors="coerce"),
                            "2026采购金额": pd.to_numeric(purchase_meta.get("2026采购金额"), errors="coerce"),
                            "2026加权采购单价": unit_price,
                            "2026加权降本单价": delta_unit,
                            "最近入库日期": normalize_text(purchase_meta.get("最近入库日期", "")),
                            "单机总入库成本": None if pd.isna(unit_price) else round(acc_qty * float(unit_price), 4),
                            "单机降本金额": None if pd.isna(delta_unit) else round(acc_qty * float(delta_unit), 4),
                        }
                    )
                    continue

                if child not in graph:
                    unpriced_rows.append(
                        {
                            "产品线": product_line,
                            "整机物料编码": target,
                            "整机物料名称": root_name,
                            "未命中物料编码": child,
                            "未命中物料名称": edge.child_name,
                            "BOM层级": level + 1,
                            "累计用量": round(acc_qty, 5),
                            "路径": " -> ".join(current_path),
                            "说明": "叶子件未在采购成本表命中",
                        }
                    )
                    continue

                stack.append((child, acc_qty, level + 1, current_path))

    detail_df = pd.DataFrame(detail_rows)
    unpriced_df = pd.DataFrame(unpriced_rows)
    if not detail_df.empty:
        detail_df["单机总降本金额（负）"] = -detail_df["单机降本金额"]
        detail_df["单机涨价金额"] = detail_df["单机降本金额"].where(detail_df["单机降本金额"] > 0)
        detail_df["单机降价金额（负）"] = (-detail_df["单机降本金额"]).where(detail_df["单机降本金额"] < 0)
        detail_df["单机降本百分比"] = detail_df["单机总降本金额（负）"] / detail_df["单机总入库成本"].replace({0: pd.NA})

    summary_rows: list[dict] = []
    for target in [normalize_text(t) for t in targets]:
        target_meta = material_map.get(target, {})
        root_name = normalize_text(target_meta.get("名称", "")) or bom_name_map.get(target, "")
        product_line = normalize_text(target_meta.get("产品线", ""))
        scoped = detail_df[detail_df["整机物料编码"] == target].copy() if not detail_df.empty else pd.DataFrame()
        scoped_unpriced = unpriced_df[unpriced_df["整机物料编码"] == target].copy() if not unpriced_df.empty else pd.DataFrame()

        total_cost = pd.to_numeric(scoped.get("单机总入库成本"), errors="coerce").sum(min_count=1) if not scoped.empty else pd.NA
        total_negative = pd.to_numeric(scoped.get("单机总降本金额（负）"), errors="coerce").sum(min_count=1) if not scoped.empty else pd.NA
        total_up = pd.to_numeric(scoped.get("单机涨价金额"), errors="coerce").sum(min_count=1) if not scoped.empty else pd.NA
        total_down = pd.to_numeric(scoped.get("单机降价金额（负）"), errors="coerce").sum(min_count=1) if not scoped.empty else pd.NA
        ratio = (total_negative / total_cost) if pd.notna(total_cost) and total_cost not in (0, 0.0) and pd.notna(total_negative) else pd.NA

        summary_rows.append(
            {
                "产品线": product_line,
                "物料编码": target,
                "物料名称": root_name,
                "采购停点物料数": 0 if scoped.empty else int(scoped["采购层级物料编码"].nunique()),
                "无价停点物料数": 0 if scoped_unpriced.empty else int(scoped_unpriced["未命中物料编码"].nunique()),
                "整机总入库成本": round(float(total_cost), 4) if pd.notna(total_cost) else pd.NA,
                "整机总降本金额（负）": round(float(total_negative), 4) if pd.notna(total_negative) else pd.NA,
                "整机降本百分比": round(float(ratio), 6) if pd.notna(ratio) else pd.NA,
                "整机供应商涨价金额": round(float(total_up), 4) if pd.notna(total_up) else pd.NA,
                "整机供应链降价金额（负）": round(float(total_down), 4) if pd.notna(total_down) else pd.NA,
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    if not detail_df.empty:
        detail_df = detail_df.sort_values(["产品线", "整机物料编码", "单机总入库成本"], ascending=[True, True, False]).reset_index(drop=True)
    if not unpriced_df.empty:
        unpriced_df = unpriced_df.sort_values(["产品线", "整机物料编码", "BOM层级", "未命中物料编码"]).reset_index(drop=True)
    return summary_df, detail_df, unpriced_df


def _rollup_machine_dashboard_by_month(
    targets: List[str],
    graph: Dict[str, List[object]],
    bom_name_map: Dict[str, str],
    material_df: pd.DataFrame,
    purchase_summary_month: pd.DataFrame,
) -> pd.DataFrame:
    _, _, normalize_text, _, q5, _ = _import_rollup_helpers()
    material_map = material_df.set_index("编码").to_dict(orient="index")
    rows: list[dict] = []

    for _, month_row in purchase_summary_month.iterrows():
        purchase_map = {
            normalize_text(month_row["物料编码"]): {
                "2026加权采购单价": pd.to_numeric(month_row.get("2026加权采购单价"), errors="coerce"),
                "2026加权降本单价": pd.to_numeric(month_row.get("2026加权降本单价"), errors="coerce"),
                "Month": normalize_text(month_row.get("Month", "")),
                "Year": month_row.get("Year"),
                "MonthNo": month_row.get("MonthNo"),
            }
        }
        # this placeholder gets rebuilt below per month slice

    for month_key, month_slice in purchase_summary_month.groupby("Month", dropna=False):
        purchase_map = month_slice.set_index("物料编码").to_dict(orient="index")
        purchased_codes = set(month_slice["物料编码"].tolist())
        year = month_slice["Year"].iloc[0] if "Year" in month_slice.columns and not month_slice.empty else pd.NA
        month_no = month_slice["MonthNo"].iloc[0] if "MonthNo" in month_slice.columns and not month_slice.empty else pd.NA
        for target in targets:
            target = normalize_text(target)
            target_meta = material_map.get(target, {})
            product_line = normalize_text(target_meta.get("产品线", ""))
            root_name = normalize_text(target_meta.get("名称", "")) or bom_name_map.get(target, "")
            total_cost = 0.0
            total_negative = 0.0
            stack: list[tuple[str, float, list[str]]] = [(target, 1.0, [target])]
            hit = False
            while stack:
                parent, parent_acc, path = stack.pop()
                for edge in graph.get(parent, []):
                    child = edge.child_code
                    if child in path:
                        continue
                    acc_qty = parent_acc * float(q5(edge.single_qty))
                    if child in purchased_codes:
                        purchase_meta = purchase_map.get(child, {})
                        unit_price = pd.to_numeric(purchase_meta.get("2026加权采购单价"), errors="coerce")
                        delta_unit = pd.to_numeric(purchase_meta.get("2026加权降本单价"), errors="coerce")
                        if pd.notna(unit_price):
                            total_cost += acc_qty * float(unit_price)
                            hit = True
                        if pd.notna(delta_unit):
                            total_negative += acc_qty * (-float(delta_unit))
                    elif child in graph:
                        stack.append((child, acc_qty, path + [child]))
            rows.append(
                {
                    "产品线": product_line,
                    "物料编码": target,
                    "物料名称": root_name,
                    "Month": month_key,
                    "Year": year,
                    "MonthNo": month_no,
                    "整机总入库成本": round(total_cost, 4) if hit else pd.NA,
                    "整机总降本金额（负）": round(total_negative, 4) if hit else pd.NA,
                }
            )

    time_df = pd.DataFrame(rows)
    if time_df.empty:
        return time_df
    time_df["整机降本百分比"] = time_df["整机总降本金额（负）"] / time_df["整机总入库成本"].replace({0: pd.NA})
    time_df = time_df.sort_values(["产品线", "物料名称", "Year", "MonthNo"]).reset_index(drop=True)
    return time_df


def _aggregate_machine_views(summary_df: pd.DataFrame, time_df: pd.DataFrame, detail_df: pd.DataFrame, unpriced_df: pd.DataFrame):
    summary_grouped = (
        summary_df.groupby(["产品线", "物料名称"], dropna=False)
        .agg(
            采购停点物料数=("采购停点物料数", "sum"),
            无价停点物料数=("无价停点物料数", "sum"),
            整机总入库成本=("整机总入库成本", "sum"),
            **{
                "整机总降本金额（负）": ("整机总降本金额（负）", "sum"),
                "整机供应商涨价金额": ("整机供应商涨价金额", "sum"),
                "整机供应链降价金额（负）": ("整机供应链降价金额（负）", "sum"),
            },
        )
        .reset_index()
    )
    summary_grouped["整机降本百分比"] = summary_grouped["整机总降本金额（负）"] / summary_grouped["整机总入库成本"].replace({0: pd.NA})

    detail_grouped = detail_df.copy()
    if not detail_grouped.empty:
        detail_grouped = detail_grouped.rename(columns={"整机物料名称": "产品"})
        detail_grouped["产品"] = detail_grouped["产品"].fillna("").astype(str)
        detail_grouped = (
            detail_grouped.groupby(
                ["产品线", "产品", "采购层级物料编码", "采购层级物料名称", "主供应商", "主SOURCING"],
                dropna=False,
                as_index=False,
            )
            .agg(
                累计用量=("累计用量", "sum"),
                **{
                    "2026加权采购单价": ("2026加权采购单价", "first"),
                    "单机总入库成本": ("单机总入库成本", "sum"),
                    "单机总降本金额（负）": ("单机总降本金额（负）", "sum"),
                    "单机涨价金额": ("单机涨价金额", "sum"),
                    "单机降价金额（负）": ("单机降价金额（负）", "sum"),
                    "最近入库日期": ("最近入库日期", "max"),
                },
            )
        )
        detail_grouped["单机降本百分比"] = detail_grouped["单机总降本金额（负）"] / detail_grouped["单机总入库成本"].replace({0: pd.NA})

    unpriced_grouped = unpriced_df.copy()
    if not unpriced_grouped.empty:
        unpriced_grouped = unpriced_grouped.rename(columns={"整机物料名称": "产品"})

    time_grouped = time_df.copy()
    if not time_grouped.empty:
        time_grouped = (
            time_grouped.groupby(["产品线", "物料名称", "Month", "Year", "MonthNo"], dropna=False)
            .agg(**{"整机总入库成本": ("整机总入库成本", "sum"), "整机总降本金额（负）": ("整机总降本金额（负）", "sum")})
            .reset_index()
        )
        time_grouped["整机降本百分比"] = time_grouped["整机总降本金额（负）"] / time_grouped["整机总入库成本"].replace({0: pd.NA})

    return summary_grouped, time_grouped, detail_grouped, unpriced_grouped


def _resolve_effective_price(price_history: pd.DataFrame, material_code: str, month_end: pd.Timestamp) -> tuple[float | None, float | None]:
    scoped = price_history[(price_history["物料编码"] == material_code) & (price_history["生效日期"] <= month_end)].copy()
    if scoped.empty:
        return None, None
    scoped = scoped.sort_values("生效日期")
    latest_price = pd.to_numeric(scoped.iloc[-1]["含税单价"], errors="coerce")
    first_price = pd.to_numeric(scoped.iloc[0]["含税单价"], errors="coerce")
    return (None if pd.isna(latest_price) else float(latest_price), None if pd.isna(first_price) else float(first_price))


def _build_machine_views_from_cost_table(
    targets: list[str],
    graph: Dict[str, List[object]],
    bom_name_map: Dict[str, str],
    material_df: pd.DataFrame,
    purchase_months: pd.DataFrame,
    price_history: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    _, _, normalize_text, _, q5, _ = _import_rollup_helpers()
    material_map = material_df.set_index("编码").to_dict(orient="index")
    months_df = (
        purchase_months[["Month", "Year", "MonthNo"]]
        .drop_duplicates()
        .dropna(subset=["Month"])
        .sort_values(["Year", "MonthNo"])
        .reset_index(drop=True)
    )

    time_rows: list[dict] = []
    latest_detail_rows: list[dict] = []
    latest_unpriced_rows: list[dict] = []

    latest_month = months_df["Month"].iloc[-1] if not months_df.empty else None

    for _, month_row in months_df.iterrows():
        month_label = month_row["Month"]
        month_end = pd.Period(str(month_label), freq="M").end_time
        for target in targets:
            target = normalize_text(target)
            target_meta = material_map.get(target, {})
            product_line = normalize_text(target_meta.get("产品线", ""))
            root_name = normalize_text(target_meta.get("名称", "")) or bom_name_map.get(target, "")
            total_cost = 0.0
            total_negative = 0.0
            total_up = 0.0
            total_down = 0.0
            hit = False
            stack: list[tuple[str, float, int, list[str]]] = [(target, 1.0, 0, [target])]

            while stack:
                parent, parent_acc, level, path = stack.pop()
                for edge in graph.get(parent, []):
                    child = edge.child_code
                    if child in path:
                        continue
                    acc_qty = parent_acc * float(q5(edge.single_qty))
                    current_path = path + [child]
                    latest_price, first_price = _resolve_effective_price(price_history, child, month_end)
                    if latest_price is not None:
                        hit = True
                        machine_cost = acc_qty * latest_price
                        baseline = first_price if first_price is not None else latest_price
                        negative_amount = acc_qty * (baseline - latest_price)
                        total_cost += machine_cost
                        total_negative += negative_amount
                        if negative_amount < 0:
                            total_up += -negative_amount
                        elif negative_amount > 0:
                            total_down += negative_amount
                        if month_label == latest_month:
                            latest_detail_rows.append(
                                {
                                    "产品线": product_line,
                                    "产品": root_name,
                                    "采购层级物料编码": child,
                                    "采购层级物料名称": edge.child_name,
                                    "主供应商": "",
                                    "主SOURCING": "",
                                    "累计用量": round(acc_qty, 5),
                                    "2026加权采购单价": round(latest_price, 4),
                                    "单机总入库成本": round(machine_cost, 4),
                                    "单机总降本金额（负）": round(negative_amount, 4),
                                    "单机降本百分比": None if machine_cost == 0 else round(negative_amount / machine_cost, 6),
                                    "单机涨价金额": round(-negative_amount, 4) if negative_amount < 0 else pd.NA,
                                    "单机降价金额（负）": round(negative_amount, 4) if negative_amount > 0 else pd.NA,
                                    "最近入库日期": month_end.strftime("%Y-%m-%d"),
                                }
                            )
                        continue

                    if child not in graph:
                        if month_label == latest_month:
                            latest_unpriced_rows.append(
                                {
                                    "产品线": product_line,
                                    "产品": root_name,
                                    "未命中物料编码": child,
                                    "未命中物料名称": edge.child_name,
                                    "BOM层级": level + 1,
                                    "累计用量": round(acc_qty, 5),
                                    "路径": " -> ".join(current_path),
                                    "说明": "截止当月末没有生效价格",
                                }
                            )
                        continue

                    stack.append((child, acc_qty, level + 1, current_path))

            time_rows.append(
                {
                    "产品线": product_line,
                    "物料名称": root_name,
                    "Month": month_label,
                    "Year": month_row["Year"],
                    "MonthNo": month_row["MonthNo"],
                    "整机总入库成本": round(total_cost, 4) if hit else pd.NA,
                    "整机总降本金额（负）": round(total_negative, 4) if hit else pd.NA,
                    "整机供应商涨价金额": round(total_up, 4) if hit else pd.NA,
                    "整机供应链降价金额（负）": round(total_down, 4) if hit else pd.NA,
                }
            )

    time_df = pd.DataFrame(time_rows)
    if not time_df.empty:
        time_df["整机降本百分比"] = time_df["整机总降本金额（负）"] / time_df["整机总入库成本"].replace({0: pd.NA})

    latest_summary = time_df.copy()
    if not latest_summary.empty and latest_month is not None:
        latest_summary = latest_summary[latest_summary["Month"] == latest_month].copy()
        latest_summary["采购停点物料数"] = (
            pd.DataFrame(latest_detail_rows).groupby("产品", dropna=False)["采购层级物料编码"].nunique().reindex(latest_summary["物料名称"]).fillna(0).astype(int).tolist()
            if latest_detail_rows
            else 0
        )
        latest_summary["无价停点物料数"] = (
            pd.DataFrame(latest_unpriced_rows).groupby("产品", dropna=False)["未命中物料编码"].nunique().reindex(latest_summary["物料名称"]).fillna(0).astype(int).tolist()
            if latest_unpriced_rows
            else 0
        )
        latest_summary = latest_summary[
            [
                "产品线",
                "物料名称",
                "采购停点物料数",
                "无价停点物料数",
                "整机总入库成本",
                "整机总降本金额（负）",
                "整机供应商涨价金额",
                "整机供应链降价金额（负）",
                "整机降本百分比",
            ]
        ].reset_index(drop=True)

    detail_df = pd.DataFrame(latest_detail_rows)
    if not detail_df.empty:
        detail_df = (
            detail_df.groupby(["产品线", "产品", "采购层级物料编码", "采购层级物料名称"], dropna=False, as_index=False)
            .agg(
                主供应商=("主供应商", "first"),
                主SOURCING=("主SOURCING", "first"),
                累计用量=("累计用量", "sum"),
                **{
                    "2026加权采购单价": ("2026加权采购单价", "first"),
                    "单机总入库成本": ("单机总入库成本", "sum"),
                    "单机总降本金额（负）": ("单机总降本金额（负）", "sum"),
                    "单机涨价金额": ("单机涨价金额", "sum"),
                    "单机降价金额（负）": ("单机降价金额（负）", "sum"),
                    "最近入库日期": ("最近入库日期", "max"),
                },
            )
        )
        detail_df["单机降本百分比"] = detail_df["单机总降本金额（负）"] / detail_df["单机总入库成本"].replace({0: pd.NA})

    unpriced_df = pd.DataFrame(latest_unpriced_rows)
    return latest_summary, time_df, detail_df, unpriced_df


@st.cache_data(show_spinner="正在计算整机采购成本与降本情况...", ttl=600)
def get_machine_costdown_bundle(
    bom_path: str = str(DEFAULT_BOM_PATH),
    material_master_path: str = str(DEFAULT_MATERIAL_MASTER_PATH),
    purchase_costdown_path: str = str(DEFAULT_PURCHASE_COSTDOWN_PATH),
    targets: tuple[str, ...] = tuple(DEFAULT_TARGETS),
) -> MachineCostdownBundle:
    try:
        build_bom_graph, load_material_master, _, preprocess_bom, _, read_bom_sheet = _import_rollup_helpers()
        bom_df = preprocess_bom(read_bom_sheet(Path(bom_path)))
        graph, bom_name_map = build_bom_graph(bom_df)
        material_df = load_material_master(Path(material_master_path))
        purchase_df = _load_purchase_costdown_enriched(Path(purchase_costdown_path))
        purchase_summary = _summarize_purchase_for_dashboard(purchase_df)
        purchase_summary_month = _summarize_purchase_for_dashboard_by_month(purchase_df)
        cost_table_url = (os.getenv("Cost_Table") or "").strip()
        if cost_table_url:
            price_history = _load_cost_table_from_bitable(cost_table_url)
            summary_df, time_df, detail_df, unpriced_df = _build_machine_views_from_cost_table(
                list(targets), graph, bom_name_map, material_df, purchase_summary_month, price_history
            )
        else:
            summary_df, detail_df, unpriced_df = _rollup_machine_dashboard(list(targets), graph, bom_name_map, material_df, purchase_summary)
            time_df = _rollup_machine_dashboard_by_month(list(targets), graph, bom_name_map, material_df, purchase_summary_month)
            summary_df, time_df, detail_df, unpriced_df = _aggregate_machine_views(summary_df, time_df, detail_df, unpriced_df)
        return MachineCostdownBundle(
            summary_df=summary_df,
            time_df=time_df,
            detail_df=detail_df,
            unpriced_df=unpriced_df,
            error=None,
            source_info={
                "bom_path": bom_path,
                "material_master_path": material_master_path,
                "purchase_costdown_path": purchase_costdown_path,
                "cost_table_url": cost_table_url,
            },
        )
    except Exception as exc:
        empty = pd.DataFrame()
        return MachineCostdownBundle(
            summary_df=empty,
            time_df=empty,
            detail_df=empty,
            unpriced_df=empty,
            error=str(exc),
            source_info={
                "bom_path": bom_path,
                "material_master_path": material_master_path,
                "purchase_costdown_path": purchase_costdown_path,
                "cost_table_url": (os.getenv("Cost_Table") or "").strip(),
            },
        )
