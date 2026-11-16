"""扫码登录状态机。

状态机（协议端实测 loginState 取值）：
    waiting                  等待扫码
    login_processing         已扫码，处理中
    ipad_required            需要 iPad 二次确认（双扫）
    online                   登录完成
    security_verify_required  需要安全验证，必须重新登录
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .client import Client

from .envelope import APIError, CodeFailGeneric, ReasonSecurityReloginNeeded


@dataclass
class LoginState:
    """扫码登录的当前状态。"""

    state: int = 0
    login_state: str = ""
    next_step: str = ""
    qr_code_url: str = ""
    wxid: str = ""
    message: str = ""
    attempt_id: str = ""

    @classmethod
    def parse(cls, data: Optional[dict]) -> "LoginState":
        d = data or {}
        return cls(
            state=int(d.get("state") or 0),
            login_state=str(d.get("loginState") or ""),
            next_step=str(d.get("nextStep") or ""),
            qr_code_url=str(d.get("qrCodeUrl") or d.get("QrCodeUrl") or ""),
            wxid=str(d.get("wxid") or ""),
            message=str(d.get("msg") or ""),
            attempt_id=str(d.get("attemptId") or ""),
        )

    @property
    def is_online(self) -> bool:
        return self.login_state == "online"

    @property
    def need_ipad_confirm(self) -> bool:
        return self.login_state == "ipad_required"

    @property
    def need_security_verify(self) -> bool:
        return self.login_state == "security_verify_required"

    @property
    def is_terminal(self) -> bool:
        return self.is_online or self.need_security_verify


class LoginService:
    """封装 /login/* 接口。"""

    def __init__(self, client: "Client") -> None:
        self._c = client

    def get_qr_code(self, device: str = "ipad") -> LoginState:
        """获取登录二维码。

        协议端要求同一 key 同时只能有一个活跃的登录尝试（15 分钟 TTL），
        调用方需要持久化返回的 attempt_id 以便后续轮询。
        """
        data = self._c._call(
            "POST", "/login/GetLoginQrCodeNewDirect", {"device": device or "ipad"}
        )
        return LoginState.parse(data)

    def check_status(self, attempt_id: str = "") -> LoginState:
        """查询登录进度。建议每 2.5 秒调用一次。"""
        body: dict = {}
        if attempt_id:
            body["attemptId"] = attempt_id
        data = self._c._call("POST", "/login/CheckLoginStatus", body)
        st = LoginState.parse(data)
        if not st.attempt_id:
            st.attempt_id = attempt_id
        return st

    def wait_for_online(
        self, attempt_id: str = "", interval: float = 2.5, timeout: float = 300.0
    ) -> LoginState:
        """阻塞等待登录完成，内部按 2.5 秒轮询。

        超时或进入不可恢复失败（security_verify_required）时抛异常。
        """
        deadline = time.monotonic() + timeout
        last = LoginState(attempt_id=attempt_id)
        while time.monotonic() < deadline:
            st = self.check_status(attempt_id)
            last = st
            if st.is_online:
                return st
            if st.need_security_verify:
                raise APIError(
                    code=CodeFailGeneric,
                    text="需要安全验证，必须重新发起登录",
                    reason_code=ReasonSecurityReloginNeeded,
                )
            time.sleep(interval)
        raise APIError(code=CodeFailGeneric, text="等待登录超时")

    def cancel(self, attempt_id: str = "") -> None:
        """取消当前登录尝试。"""
        body: dict = {}
        if attempt_id:
            body["attemptId"] = attempt_id
        self._c._call("POST", "/login/CancelLogin", body)

    def get_login_status(self) -> Any:
        """查询账号当前是否在线（不需要走扫码流程）。"""
        return self._c._call("GET", "/login/GetLoginStatus")

    def wake_up(self, attempt_id: str = "") -> LoginState:
        """唤醒已登录过的账号（避免重新扫码）。"""
        body: dict = {}
        if attempt_id:
            body["attemptId"] = attempt_id
        data = self._c._call("POST", "/login/WakeUpLogin", body)
        return LoginState.parse(data)
