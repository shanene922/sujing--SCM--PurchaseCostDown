from __future__ import annotations

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

from .metrics import aggregate_metrics


DETAIL_COLUMNS = [
    "日期",
    "SOURCING",
    "一级品类",
    "二级品类",
    "供应商名称",
    "物料编码",
    "物料名称",
    "降本类别",
    "入库金额",
    "总降本",
    "行降本百分比",
]

MATRIX_METRICS = ["总降本金额（负）", "总入库金额", "降本百分比", "加权平均入库价格"]


def _render_csv_download_button(df: pd.DataFrame, key: str, file_name: str) -> None:
    csv_bytes = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        "下载CSV",
        data=csv_bytes,
        file_name=file_name,
        mime="text/csv",
        key=f"{key}_csv_download",
    )


def render_detail_table(df: pd.DataFrame, key: str, height: int = 360, max_rows: int = 500) -> None:
    available_columns = [col for col in DETAIL_COLUMNS if col in df.columns]
    table_df = df[available_columns].copy().head(max_rows)
    if "日期" in table_df.columns:
        table_df["日期"] = pd.to_datetime(table_df["日期"], errors="coerce").dt.strftime("%Y-%m-%d")
    if "行降本百分比" in table_df.columns:
        table_df["行降本百分比"] = table_df["行降本百分比"].map(lambda x: None if pd.isna(x) else round(x * 100, 2))

    builder = GridOptionsBuilder.from_dataframe(table_df)
    builder.configure_default_column(groupable=True, sortable=True, filter=True, resizable=True)
    builder.configure_grid_options(domLayout="normal")
    if "行降本百分比" in table_df.columns:
        builder.configure_column("行降本百分比", header_name="行降本百分比(%)")
    AgGrid(
        table_df,
        gridOptions=builder.build(),
        height=height,
        theme="streamlit",
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        key=key,
    )



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


def _collapse_dimension_values(series: pd.Series) -> str:
    values = [str(v).strip() for v in series if pd.notna(v) and str(v).strip()]
    if not values:
        return ""
    unique_values = list(dict.fromkeys(values))
    return " / ".join(unique_values)


def build_matrix_dataframe(df: pd.DataFrame, row_fields: list[str], extra_columns: list[str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    if df.empty:
        return pd.DataFrame(columns=row_fields + ["_path"]), []

    scoped = _ensure_metric_numeric(df)
    scoped = scoped[scoped["Month"].notna()].copy()
    scoped["时间列"] = scoped["Month"].astype(str)
    extra_columns = [col for col in (extra_columns or []) if col in scoped.columns and col not in row_fields]

    month_order = (
        scoped[["时间列", "Year", "MonthNo"]]
        .drop_duplicates()
        .sort_values(["Year", "MonthNo"])["时间列"]
        .astype(str)
        .tolist()
    )

    month_metrics = aggregate_metrics(scoped, row_fields + ["时间列"]).rename(columns={"入库金额": "总入库金额"})
    month_metrics["时间列"] = month_metrics["时间列"].astype(str)

    total_metrics = aggregate_metrics(scoped, row_fields).rename(columns={"入库金额": "总入库金额"})
    total_metrics = total_metrics[row_fields + MATRIX_METRICS].copy()
    total_metrics = total_metrics.rename(columns={metric: f"总计|{metric}" for metric in MATRIX_METRICS})

    result = month_metrics[row_fields].drop_duplicates().reset_index(drop=True)
    if extra_columns:
        extra_df = scoped[row_fields + extra_columns].drop_duplicates().reset_index(drop=True)
        if extra_df.duplicated(subset=row_fields).any():
            extra_df = extra_df.groupby(row_fields, dropna=False, as_index=False).agg({col: _collapse_dimension_values for col in extra_columns})
        result = result.merge(extra_df, on=row_fields, how="left")
    result = result.merge(total_metrics, on=row_fields, how="left")

    for month_label in month_order:
        month_slice = month_metrics[month_metrics["时间列"] == month_label][row_fields + MATRIX_METRICS].copy()
        month_slice = month_slice.rename(columns={metric: f"{month_label}|{metric}" for metric in MATRIX_METRICS})
        result = result.merge(month_slice, on=row_fields, how="left")

    result["_path"] = result[row_fields].fillna("(空值)").astype(str).agg(" > ".join, axis=1)
    # Force matrix metric values to integers before rendering.
    metric_cols = [c for c in result.columns if "|" in c]
    for col in metric_cols:
        result[col] = pd.to_numeric(result[col], errors="coerce").round(0)
    return result, month_order



def _build_column_defs(month_order: list[str], extra_columns: list[str] | None = None) -> list[dict]:
    money_formatter = JsCode(
        """
        function(params) {
            if (params.value === null || params.value === undefined || params.value === '') return '--';
            return Number(params.value).toLocaleString('zh-CN', {maximumFractionDigits: 0});
        }
        """
    )
    percent_formatter = JsCode(
        """
        function(params) {
            if (params.value === null || params.value === undefined || params.value === '') return '--';
            return (Number(params.value) * 100).toFixed(2) + '%';
        }
        """
    )

    metric_defs = {
        "总降本金额（负）": {"minWidth": 145, "aggFunc": "sum", "valueFormatter": money_formatter},
        "总入库金额": {"minWidth": 145, "aggFunc": "sum", "valueFormatter": money_formatter},
        "降本百分比": {"minWidth": 135, "valueFormatter": percent_formatter},
        "加权平均入库价格": {"minWidth": 155, "aggFunc": "avg", "valueFormatter": money_formatter},
    }

    column_defs: list[dict] = []
    extra_columns = extra_columns or []

    total_children = []
    for metric in MATRIX_METRICS:
        total_children.append(
                {
                    "headerName": metric,
                    "field": f"总计|{metric}",
                    "type": ["numericColumn"],
                    "pinned": "left",
                    "lockPosition": "left",
                    "suppressMovable": True,
                    "enableValue": True,
                    **(
                        {
                            "valueGetter": JsCode(
                                """
                                function(params) {
                                    if (params.node && params.node.group) {
                                        const num = params.node.aggData ? params.node.aggData["总计|总降本金额（负）"] : null;
                                        const den = params.node.aggData ? params.node.aggData["总计|总入库金额"] : null;
                                        return den ? num / den : null;
                                    }
                                    return params.data ? params.data["总计|降本百分比"] : null;
                                }
                                """
                            )
                        }
                        if metric == "降本百分比"
                        else {}
                    ),
                    **metric_defs[metric],
                }
            )
    column_defs.append(
        {
            "headerName": "总计",
            "children": total_children,
            "marryChildren": True,
            "headerClass": "ag-center-header",
        }
    )

    for col in extra_columns:
        column_defs.append(
            {
                "headerName": col,
                "field": col,
                "minWidth": 130,
                "suppressMovable": True,
            }
        )

    for month in month_order:
        children = []
        for metric in MATRIX_METRICS:
            children.append(
                {
                    "headerName": metric,
                    "field": f"{month}|{metric}",
                    "type": ["numericColumn"],
                    "enableValue": True,
                    **(
                        {
                            "valueGetter": JsCode(
                                f"""
                                function(params) {{
                                    if (params.node && params.node.group) {{
                                        const num = params.node.aggData ? params.node.aggData["{month}|总降本金额（负）"] : null;
                                        const den = params.node.aggData ? params.node.aggData["{month}|总入库金额"] : null;
                                        return den ? num / den : null;
                                    }}
                                    return params.data ? params.data["{month}|降本百分比"] : null;
                                }}
                                """
                            )
                        }
                        if metric == "降本百分比"
                        else {}
                    ),
                    **metric_defs[metric],
                }
            )
        column_defs.append(
            {
                "headerName": month,
                "children": children,
                "marryChildren": True,
                "headerClass": "ag-center-header",
            }
        )

    return column_defs


def _build_pinned_total_row(df: pd.DataFrame, label_field: str, label_text: str = "总计") -> dict:
    total_row: dict = {label_field: label_text}
    value_cols = [c for c in df.columns if "|" in c]
    for col in value_cols:
        metric = col.split("|", 1)[1]
        prefix = col.split("|", 1)[0]
        if metric == "降本百分比":
            num_col = f"{prefix}|总降本金额（负）"
            den_col = f"{prefix}|总入库金额"
            num = pd.to_numeric(df[num_col], errors="coerce").sum() if num_col in df.columns else 0
            den = pd.to_numeric(df[den_col], errors="coerce").sum() if den_col in df.columns else 0
            total_row[col] = (num / den) if den not in (0, 0.0) else None
        elif metric == "加权平均入库价格":
            total_row[col] = pd.to_numeric(df[col], errors="coerce").mean()
        else:
            total_row[col] = pd.to_numeric(df[col], errors="coerce").sum()
    return total_row


def _build_left_pinned_state(extra_columns: list[str] | None = None) -> str:
    ordered_left_cols = [
        "总计|总降本金额（负）",
        "总计|总入库金额",
        "总计|降本百分比",
        "总计|加权平均入库价格",
    ]
    cols_js = ", ".join([f'"{col}"' for col in ordered_left_cols])
    return f"""
        function(params) {{
            const state = [{{ colId: "ag-Grid-AutoColumn", pinned: "left" }}];
            [{cols_js}].forEach(function(colId) {{
                if (params.columnApi.getColumn(colId)) {{
                    state.push({{ colId: colId, pinned: "left" }});
                }}
            }});
            params.columnApi.applyColumnState({{ state: state, applyOrder: true }});
        }}
    """



def render_matrix_table(
    df: pd.DataFrame,
    key: str,
    row_fields: list[str],
    grain: str = "月份",
    height: int = 480,
    extra_columns: list[str] | None = None,
) -> None:
    matrix_df, month_order = build_matrix_dataframe(df, row_fields, extra_columns=extra_columns)
    export_df = matrix_df.drop(columns=["_path"], errors="ignore")
    _render_csv_download_button(export_df, key=f"{key}_matrix", file_name=f"{key}.csv")

    builder = GridOptionsBuilder.from_dataframe(matrix_df)
    builder.configure_default_column(sortable=True, filter=True, resizable=True)

    extra_columns = [col for col in (extra_columns or []) if col in matrix_df.columns and col not in row_fields]
    for col in row_fields:
        builder.configure_column(col, hide=True)
    builder.configure_column("_path", hide=True)

    grid_options = builder.build()
    grid_options["treeData"] = True
    grid_options["animateRows"] = True
    grid_options["groupDefaultExpanded"] = 0
    grid_options["suppressAggFuncInHeader"] = True
    grid_options["getDataPath"] = JsCode("function(data) { return data._path.split(' > '); }")
    grid_options["autoGroupColumnDef"] = {
        "headerName": "层级",
        "minWidth": 280,
        "cellRendererParams": {"suppressCount": True},
        "pinned": "left",
        "lockPosition": "left",
        "suppressMovable": True,
    }
    grid_options["columnDefs"] = _build_column_defs(month_order, extra_columns=extra_columns)
    grid_options["onFirstDataRendered"] = JsCode(_build_left_pinned_state(extra_columns=extra_columns))
    total_row = _build_pinned_total_row(matrix_df, label_field="_path", label_text="总计")
    if row_fields:
        total_row[row_fields[0]] = "总计"
    grid_options["pinnedBottomRowData"] = [total_row]

    AgGrid(
        matrix_df,
        gridOptions=grid_options,
        height=height,
        theme="streamlit",
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        key=key,
        enable_enterprise_modules=True,
    )


def render_supplier_material_matrix(
    df: pd.DataFrame,
    key: str,
    height: int = 480,
    sourcing_column: str = "SOURCING",
) -> None:
    row_fields = ["供应商名称", "物料编码名称"]
    matrix_df, month_order = build_matrix_dataframe(df, row_fields, extra_columns=[sourcing_column])
    export_df = matrix_df.drop(columns=["_path"], errors="ignore")
    _render_csv_download_button(export_df, key=f"{key}_matrix", file_name=f"{key}.csv")
    choice = st.radio(
        "层级显示",
        options=["默认折叠", "全部展开"],
        horizontal=True,
        key=f"{key}_expand_toggle",
    )
    expand_all = choice == "全部展开"
    expand_level = -1 if expand_all else 0
    money_formatter = JsCode(
        """
        function(params) {
            if (params.value === null || params.value === undefined || params.value === '') return '--';
            return Number(params.value).toLocaleString('zh-CN', {maximumFractionDigits: 0});
        }
        """
    )
    percent_formatter = JsCode(
        """
        function(params) {
            if (params.value === null || params.value === undefined || params.value === '') return '--';
            return (Number(params.value) * 100).toFixed(2) + '%';
        }
        """
    )
    metric_defs = {
        "总降本金额（负）": {"minWidth": 145, "valueFormatter": money_formatter, "aggFunc": "sum"},
        "总入库金额": {"minWidth": 145, "valueFormatter": money_formatter, "aggFunc": "sum"},
        "降本百分比": {"minWidth": 135, "valueFormatter": percent_formatter},
        "加权平均入库价格": {"minWidth": 155, "valueFormatter": money_formatter, "aggFunc": "avg"},
    }

    column_defs: list[dict] = []
    column_defs.append(
        {
            "headerName": "总计",
            "children": [
                {
                    "headerName": metric,
                    "field": f"总计|{metric}",
                    "type": ["numericColumn"],
                    "enableValue": True,
                    **(
                        {
                            "valueGetter": JsCode(
                                """
                                function(params) {
                                    if (params.node && params.node.group) {
                                        const num = params.node.aggData ? params.node.aggData["总计|总降本金额（负）"] : null;
                                        const den = params.node.aggData ? params.node.aggData["总计|总入库金额"] : null;
                                        return den ? num / den : null;
                                    }
                                    return params.data ? params.data["总计|降本百分比"] : null;
                                }
                                """
                            )
                        }
                        if metric == "降本百分比"
                        else {}
                    ),
                    **metric_defs[metric],
                }
                for metric in MATRIX_METRICS
            ],
            "marryChildren": True,
            "headerClass": "ag-center-header",
        }
    )
    if sourcing_column in matrix_df.columns:
        column_defs.append(
            {
                "headerName": sourcing_column,
                "field": sourcing_column,
                "minWidth": 140,
                "suppressMovable": True,
            }
        )
    for month in month_order:
        column_defs.append(
            {
                "headerName": month,
                "children": [
                    {
                        "headerName": metric,
                        "field": f"{month}|{metric}",
                        "type": ["numericColumn"],
                        "enableValue": True,
                        **(
                            {
                                "valueGetter": JsCode(
                                    f"""
                                    function(params) {{
                                        if (params.node && params.node.group) {{
                                            const num = params.node.aggData ? params.node.aggData["{month}|总降本金额（负）"] : null;
                                            const den = params.node.aggData ? params.node.aggData["{month}|总入库金额"] : null;
                                            return den ? num / den : null;
                                        }}
                                        return params.data ? params.data["{month}|降本百分比"] : null;
                                    }}
                                    """
                                )
                            }
                            if metric == "降本百分比"
                            else {}
                        ),
                        **metric_defs[metric],
                    }
                    for metric in MATRIX_METRICS
                ],
                "marryChildren": True,
                "headerClass": "ag-center-header",
            }
        )

    grid_options = {
        "columnDefs": column_defs,
        "defaultColDef": {"sortable": True, "filter": True, "resizable": True},
        "treeData": True,
        "animateRows": True,
        "groupDefaultExpanded": expand_level,
        "suppressAggFuncInHeader": True,
        "maintainColumnOrder": True,
        "ensureDomOrder": True,
        "suppressMovableColumns": True,
        "getDataPath": JsCode("function(data) { return data._path.split(' > '); }"),
    }
    grid_options["treeData"] = True
    grid_options["autoGroupColumnDef"] = {
        "headerName": "层级",
        "minWidth": 320,
        "cellRendererParams": {"suppressCount": True},
        "pinned": "left",
        "lockPosition": "left",
        "suppressMovable": True,
    }
    grid_options["onFirstDataRendered"] = JsCode(
        f"""
        function(params) {{
            ({_build_left_pinned_state(extra_columns=[sourcing_column])})(params);
            if ({str(expand_all).lower()}) {{
                params.api.expandAll();
            }} else {{
                params.api.collapseAll();
            }}
            params.api.refreshHeader();
        }}
        """
    )
    total_row = _build_pinned_total_row(matrix_df, label_field="_path", label_text="总计")
    total_row["供应商名称"] = "总计"
    grid_options["pinnedBottomRowData"] = [total_row]

    AgGrid(
        matrix_df,
        gridOptions=grid_options,
        height=height,
        theme="streamlit",
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        key=f"{key}_{'expanded' if expand_all else 'collapsed'}",
        enable_enterprise_modules=True,
        reload_data=True,
    )


def render_sourcing_month_matrix(df: pd.DataFrame, key: str, height: int = 480) -> None:
    scoped = _ensure_metric_numeric(df)
    scoped = scoped[scoped["Month"].notna() & scoped["SOURCING"].notna()].copy()
    if scoped.empty:
        AgGrid(pd.DataFrame(), gridOptions={}, height=height, theme="streamlit", key=key)
        return

    scoped["月份"] = scoped["Month"].astype(str)
    month_order = (
        scoped[["月份", "Year", "MonthNo"]]
        .drop_duplicates()
        .sort_values(["Year", "MonthNo"])["月份"]
        .astype(str)
        .tolist()
    )
    sourcing_order = sorted(scoped["SOURCING"].astype(str).dropna().unique().tolist())

    month_source = aggregate_metrics(scoped, ["月份", "SOURCING"]).rename(columns={"入库金额": "总入库金额"})
    month_total = aggregate_metrics(scoped, ["月份"]).rename(columns={"入库金额": "总入库金额"})

    result = pd.DataFrame({"月份": month_order})
    total_map = month_total.set_index("月份")[MATRIX_METRICS]
    for metric in MATRIX_METRICS:
        result[f"总计|{metric}"] = result["月份"].map(total_map[metric] if metric in total_map.columns else pd.Series(dtype="float64"))

    for source in sourcing_order:
        source_df = month_source[month_source["SOURCING"].astype(str) == str(source)]
        source_map = source_df.set_index("月份")[MATRIX_METRICS]
        for metric in MATRIX_METRICS:
            result[f"{source}|{metric}"] = result["月份"].map(source_map[metric] if metric in source_map.columns else pd.Series(dtype="float64"))

    value_cols = [c for c in result.columns if "|" in c]
    for col in value_cols:
        result[col] = pd.to_numeric(result[col], errors="coerce").round(0)

    money_formatter = JsCode(
        """
        function(params) {
            if (params.value === null || params.value === undefined || params.value === '') return '--';
            return Number(params.value).toLocaleString('zh-CN', {maximumFractionDigits: 0});
        }
        """
    )
    percent_formatter = JsCode(
        """
        function(params) {
            if (params.value === null || params.value === undefined || params.value === '') return '--';
            return (Number(params.value) * 100).toFixed(2) + '%';
        }
        """
    )

    def metric_col(metric: str, field: str, pinned_left: bool = False) -> dict:
        formatter = percent_formatter if metric == "降本百分比" else money_formatter
        col_def = {
            "headerName": metric,
            "field": field,
            "type": ["numericColumn"],
            "valueFormatter": formatter,
            "minWidth": 145 if metric != "降本百分比" else 135,
        }
        if pinned_left:
            col_def.update({"pinned": "left", "lockPosition": "left", "suppressMovable": True})
        return col_def

    col_defs = [
        {"headerName": "月份", "field": "月份", "pinned": "left", "minWidth": 110},
        {
            "headerName": "总计",
            "children": [metric_col(m, f"总计|{m}", pinned_left=True) for m in MATRIX_METRICS],
            "marryChildren": True,
            "headerClass": "ag-center-header",
        },
    ]
    for source in sourcing_order:
        col_defs.append(
            {
                "headerName": str(source),
                "children": [metric_col(m, f"{source}|{m}") for m in MATRIX_METRICS],
                "marryChildren": True,
                "headerClass": "ag-center-header",
            }
        )

    grid_options = {
        "columnDefs": col_defs,
        "defaultColDef": {"sortable": True, "filter": True, "resizable": True},
        "animateRows": True,
        "suppressAggFuncInHeader": True,
    }
    grid_options["pinnedBottomRowData"] = [_build_pinned_total_row(result, label_field="月份", label_text="总计")]
    _render_csv_download_button(result, key=f"{key}_matrix", file_name=f"{key}.csv")

    AgGrid(
        result,
        gridOptions=grid_options,
        height=height,
        theme="streamlit",
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        key=key,
        enable_enterprise_modules=True,
    )


def render_category_overview_table(df: pd.DataFrame, key: str, height: int = 460) -> None:
    scoped = _ensure_metric_numeric(df)
    category_fields = [field for field in ["一级品类", "二级品类"] if field in scoped.columns]
    if len(category_fields) < 2:
        st.info("当前数据缺少 `一级品类` 或 `二级品类` 字段，暂时无法展示品类降本情况。")
        return

    scoped["一级品类"] = scoped["一级品类"].fillna("(空值)").astype(str)
    scoped["二级品类"] = scoped["二级品类"].fillna("(空值)").astype(str)

    result = aggregate_metrics(scoped, ["一级品类", "二级品类"]).rename(columns={"入库金额": "总入库金额"})
    result = result[["一级品类", "二级品类", "总降本金额（负）", "总入库金额", "降本百分比"]].copy()
    for col in ["总降本金额（负）", "总入库金额", "降本百分比"]:
        result[col] = pd.to_numeric(result[col], errors="coerce").round(4 if col == "降本百分比" else 0)
    result = result.sort_values(["总降本金额（负）", "总入库金额"], ascending=[False, False]).reset_index(drop=True)
    result["_path"] = result[["一级品类", "二级品类"]].agg(" > ".join, axis=1)

    export_df = result.drop(columns=["_path"], errors="ignore")
    _render_csv_download_button(export_df, key=f"{key}_csv", file_name=f"{key}.csv")

    money_formatter = JsCode(
        """
        function(params) {
            if (params.value === null || params.value === undefined || params.value === '') return '--';
            return Number(params.value).toLocaleString('zh-CN', {maximumFractionDigits: 0});
        }
        """
    )
    percent_formatter = JsCode(
        """
        function(params) {
            if (params.value === null || params.value === undefined || params.value === '') return '--';
            return (Number(params.value) * 100).toFixed(2) + '%';
        }
        """
    )

    builder = GridOptionsBuilder.from_dataframe(result)
    builder.configure_default_column(sortable=True, filter=True, resizable=True)
    builder.configure_column("一级品类", hide=True)
    builder.configure_column("二级品类", hide=True)
    builder.configure_column("_path", hide=True)

    grid_options = builder.build()
    grid_options["treeData"] = True
    grid_options["animateRows"] = True
    grid_options["groupDefaultExpanded"] = 0
    grid_options["suppressAggFuncInHeader"] = True
    grid_options["getDataPath"] = JsCode("function(data) { return data._path.split(' > '); }")
    grid_options["autoGroupColumnDef"] = {
        "headerName": "品类层级",
        "minWidth": 320,
        "cellRendererParams": {"suppressCount": True},
        "pinned": "left",
        "lockPosition": "left",
        "suppressMovable": True,
    }
    grid_options["columnDefs"] = [
        {
            "headerName": "品类层级",
            "field": "一级品类",
            "hide": True,
        },
        {
            "headerName": "总降本金额（负）",
            "field": "总降本金额（负）",
            "type": ["numericColumn"],
            "valueFormatter": money_formatter,
            "minWidth": 180,
        },
        {
            "headerName": "总入库金额",
            "field": "总入库金额",
            "type": ["numericColumn"],
            "valueFormatter": money_formatter,
            "minWidth": 170,
        },
        {
            "headerName": "降本百分比",
            "field": "降本百分比",
            "type": ["numericColumn"],
            "valueFormatter": percent_formatter,
            "minWidth": 140,
        },
    ]
    total_row = {
        "_path": "总计",
        "一级品类": "总计",
        "总降本金额（负）": pd.to_numeric(result["总降本金额（负）"], errors="coerce").sum(),
        "总入库金额": pd.to_numeric(result["总入库金额"], errors="coerce").sum(),
    }
    total_row["降本百分比"] = (
        total_row["总降本金额（负）"] / total_row["总入库金额"]
        if total_row["总入库金额"] not in (0, 0.0)
        else None
    )
    grid_options["pinnedBottomRowData"] = [total_row]

    AgGrid(
        result,
        gridOptions=grid_options,
        height=height,
        theme="streamlit",
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        key=key,
        enable_enterprise_modules=True,
    )


def render_machine_cost_matrix(df: pd.DataFrame, key: str, height: int = 520) -> None:
    if df.empty:
        AgGrid(pd.DataFrame(), gridOptions={}, height=height, theme="streamlit", key=key)
        return

    scoped = df.copy()
    if "产品" not in scoped.columns:
        scoped["产品"] = scoped["整机物料名称"].fillna("").astype(str)
    if "采购停点物料" not in scoped.columns:
        scoped["采购停点物料"] = scoped["采购层级物料编码"].fillna("").astype(str) + " | " + scoped["采购层级物料名称"].fillna("").astype(str)
    scoped["_path"] = scoped[["产品线", "产品", "采购停点物料"]].fillna("(空值)").astype(str).agg(" > ".join, axis=1)

    export_df = scoped[
        [
            "产品线",
            "产品",
            "采购停点物料",
            "主供应商",
            "主SOURCING",
            "累计用量",
            "2026加权采购单价",
            "单机总入库成本",
            "单机总降本金额（负）",
            "单机降本百分比",
            "单机涨价金额",
            "单机降价金额（负）",
            "最近入库日期",
        ]
    ].copy()
    _render_csv_download_button(export_df, key=f"{key}_csv", file_name=f"{key}.csv")

    money_formatter = JsCode(
        """
        function(params) {
            if (params.value === null || params.value === undefined || params.value === '') return '--';
            return Number(params.value).toLocaleString('zh-CN', {maximumFractionDigits: 0});
        }
        """
    )
    percent_formatter = JsCode(
        """
        function(params) {
            if (params.value === null || params.value === undefined || params.value === '') return '--';
            return (Number(params.value) * 100).toFixed(2) + '%';
        }
        """
    )
    qty_formatter = JsCode(
        """
        function(params) {
            if (params.value === null || params.value === undefined || params.value === '') return '--';
            return Number(params.value).toLocaleString('zh-CN', {maximumFractionDigits: 0});
        }
        """
    )

    builder = GridOptionsBuilder.from_dataframe(scoped)
    builder.configure_default_column(sortable=True, filter=True, resizable=True)
    for col in ["产品线", "产品", "采购停点物料", "_path", "整机物料编码", "整机物料名称", "采购层级物料编码", "采购层级物料名称", "路径"]:
        if col in scoped.columns:
            builder.configure_column(col, hide=True)

    grid_options = builder.build()
    grid_options["treeData"] = True
    grid_options["animateRows"] = True
    grid_options["groupDefaultExpanded"] = 0
    grid_options["getDataPath"] = JsCode("function(data) { return data._path.split(' > '); }")
    grid_options["autoGroupColumnDef"] = {
        "headerName": "层级",
        "minWidth": 320,
        "cellRendererParams": {"suppressCount": True},
        "pinned": "left",
        "lockPosition": "left",
        "suppressMovable": True,
    }
    grid_options["columnDefs"] = [
        {"headerName": "主供应商", "field": "主供应商", "minWidth": 180},
        {"headerName": "主SOURCING", "field": "主SOURCING", "minWidth": 140},
        {"headerName": "累计用量", "field": "累计用量", "type": ["numericColumn"], "valueFormatter": qty_formatter, "minWidth": 110},
        {"headerName": "2026加权采购单价", "field": "2026加权采购单价", "type": ["numericColumn"], "valueFormatter": money_formatter, "minWidth": 160},
        {"headerName": "单机总入库成本", "field": "单机总入库成本", "type": ["numericColumn"], "valueFormatter": money_formatter, "minWidth": 150},
        {"headerName": "单机总降本金额（负）", "field": "单机总降本金额（负）", "type": ["numericColumn"], "valueFormatter": money_formatter, "minWidth": 170},
        {"headerName": "单机降本百分比", "field": "单机降本百分比", "type": ["numericColumn"], "valueFormatter": percent_formatter, "minWidth": 140},
        {"headerName": "单机涨价金额", "field": "单机涨价金额", "type": ["numericColumn"], "valueFormatter": money_formatter, "minWidth": 140},
        {"headerName": "单机降价金额（负）", "field": "单机降价金额（负）", "type": ["numericColumn"], "valueFormatter": money_formatter, "minWidth": 160},
        {"headerName": "最近入库日期", "field": "最近入库日期", "minWidth": 120},
    ]

    AgGrid(
        scoped,
        gridOptions=grid_options,
        height=height,
        theme="streamlit",
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        key=key,
        enable_enterprise_modules=True,
    )
