"""Client 入口与统一调用出口。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlencode, urljoin

try:
    import urllib.request as _urllib_request
    import urllib.error as _urllib_error
except ImportError:  # pragma: no cover
    raise

from .envelope import APIError, CodeFailGeneric, Envelope, error_from_envelope
from .ratelimit import RateLimiter


@dataclass
class ClientOptions:
    """客户端可选配置。"""

    timeout: float = 30.0
    """单次请求超时（秒）。"""

    rate_limit_per_minute: int = 40
    """每分钟最多请求数；设为 0 关闭限速（请自行承担风控风险）。"""

    user_agent: str = "weixun-python/0.1.0"

    retries: int = 0
    """失败重试次数。默认 0——协议端不做幂等，重试需要调用方自己判断。"""


class Client:
    """微寻微信协议 API 客户端。

    baseURL 形如 ``http://127.0.0.1:7006``，不要带 ``/api`` 或 ``/v1`` 前缀
    （协议端实测 apiVersion 为空）。
    """

    def __init__(
        self,
        base_url: str,
        license_key: str,
        options: Optional[ClientOptions] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._key = license_key
        self.options = options or ClientOptions()
        self._limiter: Optional[RateLimiter] = (
            RateLimiter(self.options.rate_limit_per_minute, 60.0)
            if self.options.rate_limit_per_minute > 0
            else None
        )

        # 业务模块（延迟导入避免循环）
        from .login import LoginService
        from .message import MessageService
        from .upload import UploadService

        self.message = MessageService(self)
        self.login = LoginService(self)
        self.upload = UploadService(self)

    # ── 内部调用出口 ──────────────────────────────────

    def _call(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        raw_response: bool = False,
    ) -> Any:
        """所有业务请求的统一出口。

        做四件事：拼 URL（baseURL + path + ?key=）、限速、解析信封、按真实语义判成败。
        """
        if self._limiter is not None:
            self._limiter.acquire()

        url = urljoin(self.base_url + "/", path.lstrip("/"))
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{urlencode({'key': self._key})}"

        data = None
        headers = {
            "Accept": "application/json",
            "User-Agent": self.options.user_agent,
        }
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = _urllib_request.Request(url, data=data, headers=headers, method=method)

        try:
            with _urllib_request.urlopen(req, timeout=self.options.timeout) as resp:
                status = resp.status
                payload = resp.read()
        except _urllib_error.HTTPError as exc:
            status = exc.code
            payload = exc.read()
        except _urllib_error.URLError as exc:
            raise APIError(code=CodeFailGeneric, text=f"请求失败: {exc.reason}") from exc

        # 非 JSON 响应（协议端个别路径返回 {"error":...} 或裸文本）
        if not payload or payload[:1] != b"{":
            try:
                text = payload.decode("utf-8", errors="replace").strip()
            except Exception:
                text = ""
            raise APIError(code=CodeFailGeneric, text=text, status_code=status, body=payload)

        try:
            doc = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise APIError(
                code=CodeFailGeneric,
                text=f"响应不是合法 JSON: {exc}",
                status_code=status,
                body=payload,
            ) from exc

        env = Envelope.parse(doc)
        if not env.ok():
            raise error_from_envelope(env, status, payload)

        if raw_response:
            return env.data
        return env.data

    def _read_envelope(self, resp) -> Any:
        """从已打开的响应读信封（供 multipart 上传复用）。"""
        try:
            status = resp.status
            payload = resp.read()
        finally:
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass
        if not payload or payload[:1] != b"{":
            raise APIError(
                code=CodeFailGeneric,
                text=payload.decode("utf-8", errors="replace").strip(),
                status_code=status,
                body=payload,
            )
        env = Envelope.parse(json.loads(payload))
        if not env.ok():
            raise error_from_envelope(env, status, payload)
        return env.data

    # ── 元信息 ────────────────────────────────────────

    @property
    def key_masked(self) -> str:
        """脱敏后的 key，用于日志。"""
        k = self._key
        if len(k) <= 8:
            return "****"
        return f"{k[:4]}****{k[-4:]}"

    def __repr__(self) -> str:
        return f"Client(base_url={self.base_url!r}, key={self.key_masked})"
