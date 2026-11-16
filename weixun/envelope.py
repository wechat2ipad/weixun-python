"""统一响应信封与错误类型。

协议端实测的判定语义：
  1. Code 存在且为 0 或 200 → 成功
  2. Code 不存在 → 回退 Success == true
  3. 都无法判定 → 失败

关键反例：/user/SetProxy 返回 Code=200 但 Success=false（Go 布尔零值），
所以不能单看 Success。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# ── 协议端业务码（取自 api/vo/vo.go）────────────────────
CodeSuccess = 200
CodeLegacyOK = 0
CodeFailData = -1
CodeFailKey = -2
CodeFailBound = -3
CodeFailOffline = -4
CodeFailNotLocal = -5
CodeFailGeneric = 300

# ── 登录/代理相关的结构化原因码 ─────────────────────────
ReasonLoginSessionNotFound = "LOGIN_SESSION_NOT_FOUND"
ReasonProxyOffline = "PROXY_OFFLINE"
ReasonAttemptConflict = "ATTEMPT_CONFLICT"
ReasonAttemptMismatch = "ATTEMPT_MISMATCH"
ReasonAttemptInactive = "ATTEMPT_INACTIVE"
ReasonAttemptIDRequired = "ATTEMPT_ID_REQUIRED"
ReasonAttemptNotFound = "ATTEMPT_NOT_FOUND"
ReasonAttemptExpired = "ATTEMPT_EXPIRED"
ReasonCancelled = "CANCELLED"
ReasonWakeScanRequired = "WAKE_SCAN_REQUIRED"
ReasonSecurityReloginNeeded = "SECURITY_RELOGIN_REQUIRED"
ReasonSessionInvalid = "SESSION_INVALID"
ReasonWakeRequestFailed = "WAKE_REQUEST_FAILED"
ReasonLoginRequestFailed = "LOGIN_REQUEST_FAILED"


class APIError(Exception):
    """所有业务失败的统一异常类型。

    调用方按 ``err.code`` / ``err.reason_code`` 做分支，不要用 text 做逻辑判断。
    """

    def __init__(
        self,
        code: int,
        text: str = "",
        reason_code: str = "",
        status_code: int = 200,
        body: bytes = b"",
    ) -> None:
        self.code = code
        self.text = text
        self.reason_code = reason_code
        self.status_code = status_code
        self.body = body
        super().__init__(self.__str__())

    def __str__(self) -> str:
        if self.reason_code:
            return f"weixun: code={self.code} reason={self.reason_code} msg={self.text}"
        return f"weixun: code={self.code} msg={self.text}"

    def is_key_invalid(self) -> bool:
        """是否为 key 无效类错误，调用方据此提示重新登录。"""
        return self.code == CodeFailKey or self.reason_code == ReasonLoginSessionNotFound

    def is_rate_limited(self) -> bool:
        """是否疑似被风控限流。

        协议端本身不返回 429（无服务端限流），这里主要匹配业务文案。
        """
        if self.status_code == 429:
            return True
        return any(k in self.text for k in ("频繁", "限制", "frequency"))


@dataclass
class Envelope:
    """协议端所有业务接口的统一响应结构。"""

    code_raw: Any = None
    data: Any = None
    text: str = ""
    message: str = ""
    success: Optional[bool] = None
    reason_code: str = ""
    attempt_id: str = ""
    phase: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def parse(cls, payload: Dict[str, Any]) -> "Envelope":
        """从原始 JSON dict 构造。"""
        return cls(
            code_raw=payload.get("Code"),
            data=payload.get("Data"),
            text=payload.get("Text") or "",
            message=payload.get("Message") or "",
            success=payload.get("Success"),
            reason_code=payload.get("reasonCode") or "",
            attempt_id=payload.get("attemptId") or "",
            phase=payload.get("phase") or "",
            raw=payload,
        )

    def code(self) -> Optional[int]:
        """把 Code 解析成整数。

        协议端的 Code 可能是 200（数字）或 "200"（字符串），两种都要认。
        """
        v = self.code_raw
        if v is None:
            return None
        if isinstance(v, bool):
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            try:
                return int(s)
            except ValueError:
                return None
        return None

    def ok(self) -> bool:
        """按协议端真实语义判定成功。"""
        c = self.code()
        if c is not None:
            return c in (CodeLegacyOK, CodeSuccess)
        return self.success is True

    def message_text(self) -> str:
        """可展示的失败说明。优先 Text，回退 Message（VerifyCode 接口用 Message）。"""
        return self.text.strip() or self.message


def error_from_envelope(env: Envelope, status_code: int, body: bytes) -> APIError:
    """由响应信封构造异常。"""
    code = env.code()
    if code is None:
        code = CodeFailGeneric
    text = env.message_text()
    if not text and status_code != 200:
        text = f"HTTP {status_code}"
    return APIError(
        code=code,
        text=text,
        reason_code=env.reason_code,
        status_code=status_code,
        body=body,
    )
