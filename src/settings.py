from pathlib import Path
import os

from dotenv import load_dotenv

# 强制从“项目根目录”的 .env 加载（避免工作目录变化导致找不到 .env）
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH)

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "").strip()
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "").strip()

if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
    raise RuntimeError(
        f"缺少 FEISHU_APP_ID / FEISHU_APP_SECRET。请检查 {ENV_PATH} 是否存在且已填值。"
    )
