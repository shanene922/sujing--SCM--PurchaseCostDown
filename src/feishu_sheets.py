from __future__ import annotations

from typing import List, Any, Dict
from urllib.parse import quote
import pandas as pd

from .feishu_client import FeishuClient


def sheet_values_to_df(values: List[List[Any]], header_row_index: int = 0) -> pd.DataFrame:
    if not values or len(values) <= header_row_index:
        return pd.DataFrame()

    header = values[header_row_index]
    data_rows = values[header_row_index + 1 :]

    cols = []
    for i, h in enumerate(header):
        name = str(h).strip() if h is not None else ""
        if name == "":
            name = f"Unnamed_{i}"
        cols.append(name)

    norm_rows = []
    for r in data_rows:
        r = r or []
        if len(r) < len(cols):
            r = r + [""] * (len(cols) - len(r))
        elif len(r) > len(cols):
            r = r[: len(cols)]
        norm_rows.append(r)

    return pd.DataFrame(norm_rows, columns=cols)


def read_sheet_range(
    client: FeishuClient,
    spreadsheet_token: str,
    sheet_id: str,
    cell_range: str,
    value_render_option: str = "ToString",
    date_time_render_option: str = "FormattedString",
) -> List[List[Any]]:
    """
    正确的 v2 读范围接口：
    GET /open-apis/sheets/v2/spreadsheets/{token}/values/{sheet_id}!A1:L20
    """
    full_range = f"{sheet_id}!{cell_range}"
    encoded_range = quote(full_range, safe="")

    url = f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values/{encoded_range}"
    params: Dict[str, str] = {
        "valueRenderOption": value_render_option,
        "dateTimeRenderOption": date_time_render_option,
    }
    resp = client.request("GET", url, params=params)
    return resp.get("data", {}).get("valueRange", {}).get("values", [])


def read_sheet_as_df(
    client: FeishuClient,
    spreadsheet_token: str,
    sheet_id: str,
    cell_range: str,
    header_row_index: int = 0,
) -> pd.DataFrame:
    values = read_sheet_range(client, spreadsheet_token, sheet_id, cell_range)
    return sheet_values_to_df(values, header_row_index=header_row_index)

def write_sheet_range(
    client: FeishuClient,
    spreadsheet_token: str,
    sheet_id: str,
    cell_range: str,
    values: List[List[Any]],
    value_input_option: str = "USER_ENTERED",
) -> Dict[str, Any]:
    """
    v2 写范围接口（注意：PUT 不带 /{range}，range 在 body 里）：
    PUT /open-apis/sheets/v2/spreadsheets/{token}/values
    """
    full_range = f"{sheet_id}!{cell_range}"

    # ✅ 关键：写入的 URL 只到 /values
    url = f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values"
    params: Dict[str, str] = {"valueInputOption": value_input_option}

    payload: Dict[str, Any] = {"valueRange": {"range": full_range, "values": values}}
    return client.request("PUT", url, params=params, json=payload)


class FeishuSheetsClient:
    """Compatibility wrapper used by Streamlit dashboard modules."""

    def __init__(self, client: FeishuClient, spreadsheet_token: str):
        self.client = client
        self.spreadsheet_token = spreadsheet_token

    def read_range(
        self,
        sheet_id: str,
        cell_range: str,
        value_render_option: str = "ToString",
        date_time_render_option: str = "FormattedString",
    ) -> List[List[Any]]:
        return read_sheet_range(
            client=self.client,
            spreadsheet_token=self.spreadsheet_token,
            sheet_id=sheet_id,
            cell_range=cell_range,
            value_render_option=value_render_option,
            date_time_render_option=date_time_render_option,
        )
