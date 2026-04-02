import time
import requests
from typing import Any, Dict, Optional


class FeishuAPIError(RuntimeError):
    """Compatibility alias for modules importing FeishuAPIError."""


class FeishuClient:
    """最小封装：tenant token + 通用 request"""

    def __init__(self, app_id: str, app_secret: str, timeout: int = 30):
        self.app_id = app_id
        self.app_secret = app_secret
        self.timeout = timeout

        self._tenant_token: Optional[str] = None
        self._tenant_token_expire_at: float = 0.0

    def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        retries: int = 3,
    ) -> requests.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(retries):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json,
                    timeout=self.timeout,
                )
                if response.status_code >= 500 and attempt < retries - 1:
                    time.sleep(1.2 * (attempt + 1))
                    continue
                return response
            except requests.exceptions.RequestException as exc:
                last_exc = exc
                if attempt >= retries - 1:
                    break
                time.sleep(1.2 * (attempt + 1))

        raise FeishuAPIError(f"飞书接口网络请求失败：{last_exc}")

    def get_tenant_access_token(self) -> str:
        # 简单缓存，避免每次都打 token 接口
        now = time.time()
        if self._tenant_token and now < self._tenant_token_expire_at - 60:
            return self._tenant_token

        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}
        try:
            resp = self._request_with_retry("POST", url, json=payload)
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise FeishuAPIError(f"获取 tenant_access_token 网络失败：{exc}") from exc
        data = resp.json()

        if data.get("code") != 0:
            raise FeishuAPIError(f"获取 tenant_access_token 失败：{data}")

        token = data["tenant_access_token"]
        expire = int(data.get("expire", 0))  # 秒
        self._tenant_token = token
        self._tenant_token_expire_at = now + expire
        return token

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        token = self.get_tenant_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        resp = self._request_with_retry(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json,
        )
        try:
            data = resp.json()
        except Exception:
            data = {"_raw": resp.text}

        if not resp.ok:
            raise FeishuAPIError(f"HTTP {resp.status_code} 错误：{data}")

        if isinstance(data, dict) and data.get("code") not in (0, None):
            raise FeishuAPIError(f"飞书接口返回错误：{data}")

        return data
