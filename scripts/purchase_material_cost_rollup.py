from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import argparse
import sys

import pandas as pd


getcontext().prec = 28

REQUIRED_BOM_COLUMNS = [
    "使用组织",
    "BOM版本",
    "父项物料编码",
    "物料名称",
    "规格型号",
    "数据状态",
    "子项物料编码",
    "子项物料名称",
    "子项规格型号",
    "子项单位",
    "用量:分子",
    "用量:分母",
]
FFILL_COLUMNS = ["使用组织", "BOM版本", "父项物料编码", "物料名称", "规格型号", "数据状态"]
DECIMAL_5 = Decimal("0.00000")


@dataclass
class BomEdge:
    parent_code: str
    child_code: str
    child_name: str
    child_spec: str
    child_unit: str
    numerator: Decimal
    denominator: Decimal

    @property
    def single_qty(self) -> Decimal:
        return self.numerator / self.denominator


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def to_decimal(value: object) -> Optional[Decimal]:
    text = normalize_text(value).replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def q5(value: Decimal) -> Decimal:
    return value.quantize(DECIMAL_5, rounding=ROUND_HALF_UP)


def read_bom_sheet(xlsx_path: Path) -> pd.DataFrame:
    workbook = pd.ExcelFile(xlsx_path)
    for sheet in workbook.sheet_names:
        df = pd.read_excel(xlsx_path, sheet_name=sheet, dtype="object")
        df.columns = [normalize_text(c) for c in df.columns]
        if set(REQUIRED_BOM_COLUMNS).issubset(df.columns):
            return df
    raise RuntimeError(f"未在 {xlsx_path} 中找到包含 BOM 必需列的工作表")


def preprocess_bom(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in REQUIRED_BOM_COLUMNS:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].map(normalize_text)
    out[FFILL_COLUMNS] = out[FFILL_COLUMNS].replace("", pd.NA).ffill().fillna("")
    out = out[out["数据状态"] == "已审核"].copy()
    out = out[out["父项物料编码"] != ""].copy()
    version_map = out.groupby("父项物料编码")["BOM版本"].max()
    out["_latest_version"] = out["父项物料编码"].map(version_map)
    out = out[out["BOM版本"] == out["_latest_version"]].copy()
    return out.drop(columns=["_latest_version"])


def build_bom_graph(rows: pd.DataFrame) -> tuple[Dict[str, List[BomEdge]], Dict[str, str]]:
    graph: Dict[str, List[BomEdge]] = defaultdict(list)
    name_map: Dict[str, str] = {}
    for _, row in rows.iterrows():
        parent = normalize_text(row["父项物料编码"])
        parent_name = normalize_text(row["物料名称"])
        child = normalize_text(row["子项物料编码"])
        if parent and parent_name and parent not in name_map:
            name_map[parent] = parent_name
        if not parent or not child:
            continue
        numerator = to_decimal(row["用量:分子"])
        denominator = to_decimal(row["用量:分母"])
        if numerator is None or denominator in (None, Decimal("0")):
            continue
        graph[parent].append(
            BomEdge(
                parent_code=parent,
                child_code=child,
                child_name=normalize_text(row["子项物料名称"]),
                child_spec=normalize_text(row["子项规格型号"]),
                child_unit=normalize_text(row["子项单位"]),
                numerator=numerator,
                denominator=denominator,
            )
        )
    return graph, name_map


def load_material_master(xlsx_path: Path) -> pd.DataFrame:
    df = pd.read_excel(xlsx_path, dtype="object")
    df.columns = [normalize_text(c) for c in df.columns]
    for col in ["编码", "名称", "产品线", "一级品类", "二级品类", "物料属性"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].map(normalize_text)
    return df


def load_purchase_costdown(xlsx_path: Path) -> pd.DataFrame:
    df = pd.read_excel(xlsx_path, dtype="object")
    df.columns = [normalize_text(c) for c in df.columns]
    for col in ["物料编码", "物料名称", "供应商名称"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].map(normalize_text)
    for col in ["入库数量", "入库金额", "入库含税单价"]:
        if col not in df.columns:
            df[col] = pd.NA
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["入库日期_dt"] = pd.to_datetime(df.get("入库日期"), errors="coerce")
    return df


def summarize_purchase(df: pd.DataFrame) -> pd.DataFrame:
    valid = df[df["物料编码"].ne("") & df["入库数量"].notna() & (df["入库数量"] > 0) & df["入库金额"].notna()].copy()
    if valid.empty:
        return pd.DataFrame(columns=["物料编码", "物料名称", "2026采购数量", "2026采购金额", "2026加权采购单价", "最近入库日期"])
    grouped = (
        valid.groupby("物料编码", dropna=False)
        .agg(
            物料名称=("物料名称", "first"),
            **{
                "2026采购数量": ("入库数量", "sum"),
                "2026采购金额": ("入库金额", "sum"),
                "最近入库日期": ("入库日期_dt", "max"),
            },
        )
        .reset_index()
    )
    grouped["2026加权采购单价"] = grouped["2026采购金额"] / grouped["2026采购数量"].replace({0: pd.NA})
    grouped["最近入库日期"] = grouped["最近入库日期"].dt.strftime("%Y-%m-%d").fillna("")
    return grouped


def rollup_targets(
    targets: Iterable[str],
    graph: Dict[str, List[BomEdge]],
    bom_name_map: Dict[str, str],
    material_df: pd.DataFrame,
    purchase_summary: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
        stack: list[tuple[str, Decimal, int, list[str]]] = [(target, Decimal("1"), 0, [target])]

        while stack:
            parent, parent_acc, level, path = stack.pop()
            for edge in graph.get(parent, []):
                child = edge.child_code
                if child in path:
                    unpriced_rows.append(
                        {
                            "产品线": product_line,
                            "物料编码": target,
                            "物料名称": root_name,
                            "采购层级物料编码": child,
                            "采购层级物料名称": edge.child_name,
                            "BOM层级": level + 1,
                            "累计用量": float(q5(parent_acc * edge.single_qty)),
                            "停止原因": "循环引用",
                            "路径": " -> ".join(path + [child]),
                        }
                    )
                    continue

                acc_qty = parent_acc * edge.single_qty
                current_path = path + [child]
                if child in purchased_codes:
                    purchase_meta = purchase_map.get(child, {})
                    unit_price = pd.to_numeric(purchase_meta.get("2026加权采购单价"), errors="coerce")
                    qty_float = float(q5(acc_qty))
                    detail_rows.append(
                        {
                            "产品线": product_line,
                            "物料编码": target,
                            "物料名称": root_name,
                            "采购层级物料编码": child,
                            "采购层级物料名称": normalize_text(purchase_meta.get("物料名称", "")) or edge.child_name,
                            "BOM层级": level + 1,
                            "停止原因": "采购命中",
                            "路径": " -> ".join(current_path),
                            "累计用量": qty_float,
                            "2026采购数量": pd.to_numeric(purchase_meta.get("2026采购数量"), errors="coerce"),
                            "2026采购金额": pd.to_numeric(purchase_meta.get("2026采购金额"), errors="coerce"),
                            "2026加权采购单价": unit_price,
                            "最近入库日期": normalize_text(purchase_meta.get("最近入库日期", "")),
                            "单机采购成本": None if pd.isna(unit_price) else round(qty_float * float(unit_price), 4),
                        }
                    )
                    continue

                if child not in graph:
                    unpriced_rows.append(
                        {
                            "产品线": product_line,
                            "物料编码": target,
                            "物料名称": root_name,
                            "采购层级物料编码": child,
                            "采购层级物料名称": edge.child_name,
                            "BOM层级": level + 1,
                            "累计用量": float(q5(acc_qty)),
                            "停止原因": "叶子无采购价格",
                            "路径": " -> ".join(current_path),
                        }
                    )
                    continue

                stack.append((child, acc_qty, level + 1, current_path))

    detail_df = pd.DataFrame(detail_rows)
    unpriced_df = pd.DataFrame(unpriced_rows)

    summary_rows: list[dict] = []
    target_list = [normalize_text(t) for t in targets]
    for target in target_list:
        target_meta = material_map.get(target, {})
        root_name = normalize_text(target_meta.get("名称", "")) or bom_name_map.get(target, "")
        product_line = normalize_text(target_meta.get("产品线", ""))
        scoped_detail = detail_df[detail_df["物料编码"] == target].copy() if not detail_df.empty else pd.DataFrame()
        scoped_unpriced = unpriced_df[unpriced_df["物料编码"] == target].copy() if not unpriced_df.empty else pd.DataFrame()
        total_cost = pd.to_numeric(scoped_detail.get("单机采购成本"), errors="coerce").sum(min_count=1) if not scoped_detail.empty else pd.NA
        summary_rows.append(
            {
                "产品线": product_line,
                "物料编码": target,
                "物料名称": root_name,
                "采购停点物料数": 0 if scoped_detail.empty else int(scoped_detail["采购层级物料编码"].nunique()),
                "无价停点物料数": 0 if scoped_unpriced.empty else int(scoped_unpriced["采购层级物料编码"].nunique()),
                "单机整体采购成本": round(float(total_cost), 4) if pd.notna(total_cost) else pd.NA,
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    if not detail_df.empty:
        detail_df = detail_df.sort_values(["产品线", "物料编码", "BOM层级", "采购层级物料编码"]).reset_index(drop=True)
    if not unpriced_df.empty:
        unpriced_df = unpriced_df.sort_values(["产品线", "物料编码", "BOM层级", "采购层级物料编码"]).reset_index(drop=True)
    return summary_df, detail_df, unpriced_df


def main() -> None:
    parser = argparse.ArgumentParser(description="按真实采购停点汇总目标物料的整体采购成本")
    parser.add_argument(
        "--bom",
        type=Path,
        default=Path(r"D:\Users\Speediance\Desktop\测试\最新版本BOM.xlsx"),
        help="BOM Excel 路径",
    )
    parser.add_argument(
        "--material-master",
        type=Path,
        default=Path(r"D:\Users\Speediance\Desktop\测试\物料清单.xlsx"),
        help="物料主数据 Excel 路径",
    )
    parser.add_argument(
        "--purchase-costdown",
        type=Path,
        default=Path(r"D:\Users\Speediance\Desktop\测试\output\Purchase\purchase_costdown_20260401.xlsx"),
        help="采购成本明细 Excel 路径",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        default=["99.01.00116", "21.01.00245", "21.01.00245-A1", "21.01.00288", "21.01.00333"],
        help="目标物料编码列表",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/Purchase/material_procurement_cost_rollup.xlsx"),
        help="输出 Excel 路径",
    )
    args = parser.parse_args()

    bom_df = preprocess_bom(read_bom_sheet(args.bom))
    graph, bom_name_map = build_bom_graph(bom_df)
    material_df = load_material_master(args.material_master)
    purchase_df = load_purchase_costdown(args.purchase_costdown)
    purchase_summary = summarize_purchase(purchase_df)

    summary_df, detail_df, unpriced_df = rollup_targets(args.targets, graph, bom_name_map, material_df, purchase_summary)

    output_path = args.output if args.output.is_absolute() else Path.cwd() / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="summary")
        detail_df.to_excel(writer, index=False, sheet_name="detail")
        unpriced_df.to_excel(writer, index=False, sheet_name="unpriced")

    print(f"[saved] {output_path}")
    print("[summary]")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
