from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, parse_qs


# -----------------------------
# Sheets strict: 必须包含 sheet_id
# -----------------------------
@dataclass(frozen=True)
class SheetsRef:
    spreadsheet_token: str
    sheet_id: str


def parse_sheets_url(url: str) -> SheetsRef:
    """
    解析飞书 Sheets 链接（严格模式，必须带 sheet 参数）：
      https://xxx.feishu.cn/sheets/<spreadsheet_token>?sheet=<sheet_id>
    """
    url = url.strip()
    u = urlparse(url)

    parts = [p for p in (u.path or "").strip("/").split("/") if p]
    q = parse_qs(u.query)

    if len(parts) >= 2 and parts[0] == "sheets":
        spreadsheet_token = parts[1]
        sheet_id = (q.get("sheet") or q.get("sheet_id") or [None])[0]
        if not sheet_id:
            raise ValueError("URL 缺少 sheet 参数（?sheet=xxx）。请复制带 sheet 的表格链接。")
        return SheetsRef(spreadsheet_token=spreadsheet_token, sheet_id=sheet_id)

    raise ValueError("不是可识别的飞书 Sheets 链接（需要 /sheets/<token>?sheet=<id> 形式）。")


# -----------------------------
# Sheets loose: sheet_id 可为空（后续用 API sheets/query 自动补）
# -----------------------------
@dataclass(frozen=True)
class SheetsRefLoose:
    spreadsheet_token: str
    sheet_id: Optional[str] = None


def parse_sheets_url_loose(url: str) -> SheetsRefLoose:
    """
    解析飞书 Sheets 链接（宽松模式，允许缺少 sheet 参数）：
      - https://xxx.feishu.cn/sheets/<spreadsheet_token>?sheet=<sheet_id>
      - https://xxx.feishu.cn/sheets/<spreadsheet_token>
    """
    url = url.strip()
    u = urlparse(url)

    parts = [p for p in (u.path or "").strip("/").split("/") if p]
    q = parse_qs(u.query)

    if len(parts) >= 2 and parts[0] == "sheets":
        spreadsheet_token = parts[1]
        sheet_id = (q.get("sheet") or q.get("sheet_id") or [None])[0]
        return SheetsRefLoose(spreadsheet_token=spreadsheet_token, sheet_id=sheet_id)

    raise ValueError("不是可识别的飞书 Sheets 链接（需要 /sheets/<token> 形式）。")

