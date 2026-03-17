from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os

from dotenv import load_dotenv

from .utils import parse_feishu_sheet_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH)


@dataclass(frozen=True)
class AppConfig:
    app_id: str
    app_secret: str
    spreadsheet_token: str
    sheet_id: str
    purchase_costdown_url: str
    timeout: int = 30
    probe_rows: int = 15
    chunk_size: int = 500
    max_rows: int = 20000
    end_column: str = "ZZ"


class ConfigError(RuntimeError):
    """Raised when app configuration is invalid."""



def _get_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default



def load_config() -> AppConfig:
    app_id = _get_env("APP_ID", "FEISHU_APP_ID")
    app_secret = _get_env("APP_SECRET", "FEISHU_APP_SECRET")
    purchase_costdown_url = _get_env("Purchase_CostDown_URL")
    spreadsheet_token = _get_env("SPREADSHEET_TOKEN")
    sheet_id = _get_env("SHEET_ID")

    if (not spreadsheet_token or not sheet_id) and purchase_costdown_url:
        parsed_token, parsed_sheet = parse_feishu_sheet_url(purchase_costdown_url)
        spreadsheet_token = spreadsheet_token or parsed_token
        sheet_id = sheet_id or parsed_sheet

    missing = []
    if not app_id:
        missing.append("APP_ID / FEISHU_APP_ID")
    if not app_secret:
        missing.append("APP_SECRET / FEISHU_APP_SECRET")
    if not spreadsheet_token:
        missing.append("SPREADSHEET_TOKEN or Purchase_CostDown_URL")
    if not sheet_id:
        missing.append("SHEET_ID or Purchase_CostDown_URL")

    if missing:
        raise ConfigError(
            "缺少必要配置：" + "，".join(missing) + f"。请检查 {ENV_PATH}。"
        )

    return AppConfig(
        app_id=app_id,
        app_secret=app_secret,
        spreadsheet_token=spreadsheet_token,
        sheet_id=sheet_id,
        purchase_costdown_url=purchase_costdown_url,
        timeout=int(_get_env("FEISHU_TIMEOUT", default="30") or 30),
        probe_rows=int(_get_env("FEISHU_PROBE_ROWS", default="15") or 15),
        chunk_size=int(_get_env("FEISHU_CHUNK_SIZE", default="500") or 500),
        max_rows=int(_get_env("FEISHU_MAX_ROWS", default="20000") or 20000),
    )
