"""微寻微信协议 API 的 Python SDK。

快速开始：

    from weixun import Client, SendTextRequest

    c = Client("http://127.0.0.1:7006", "你的协议 license Key")
    res = c.message.send_text(SendTextRequest(to="wxid_xxx", text="订单已发货"))
    if not res.ok:
        print(res.error_message)

设计要点（均来自协议端实测）：
  - license key 一律走 query 参数 key
  - HTTP 状态码几乎恒为 200，成败看响应体的 Code
  - Code 可能是数字也可能是字符串 "200"
  - 64 位 ID 一律用字符串，避免精度丢失（Python int 本身无溢出，但保持跨语言一致）
  - 协议端完全不限流，SDK 默认 40 条/分钟
"""

from __future__ import annotations

__version__ = "0.1.0"

from .client import Client, ClientOptions
from .envelope import (
    Envelope,
    APIError,
    CodeSuccess,
    CodeLegacyOK,
    CodeFailData,
    CodeFailKey,
    CodeFailBound,
    CodeFailOffline,
    CodeFailNotLocal,
    CodeFailGeneric,
    ReasonLoginSessionNotFound,
    ReasonProxyOffline,
    ReasonAttemptConflict,
    ReasonAttemptMismatch,
    ReasonAttemptInactive,
    ReasonAttemptIDRequired,
    ReasonAttemptNotFound,
    ReasonAttemptExpired,
    ReasonCancelled,
    ReasonWakeScanRequired,
    ReasonSecurityReloginNeeded,
    ReasonSessionInvalid,
    ReasonWakeRequestFailed,
    ReasonLoginRequestFailed,
)
from .message import (
    MessageService,
    SendTextRequest,
    SendTextResult,
    MsgTypeText,
    MsgTypeImage,
    MsgTypeVoice,
    MsgTypeCard,
    MsgTypeVideo,
    MsgTypeSticker,
    MsgTypeLocation,
    MsgTypeApp,
    MsgTypeSystem,
    MsgTypeRevoke,
)
from .ratelimit import RateLimiter
from .stream import Stream, StreamOptions, Message, RecordContentEvent
from .login import LoginService, LoginState
from .upload import UploadService, FileTypeImage, FileTypeVideo, FileTypeFile

__all__ = [
    "Client",
    "ClientOptions",
    "Envelope",
    "APIError",
    "MessageService",
    "SendTextRequest",
    "SendTextResult",
    "RateLimiter",
    "Stream",
    "StreamOptions",
    "Message",
    "RecordContentEvent",
    "LoginService",
    "LoginState",
    "UploadService",
    # 业务码
    "CodeSuccess",
    "CodeLegacyOK",
    "CodeFailData",
    "CodeFailKey",
    "CodeFailBound",
    "CodeFailOffline",
    "CodeFailNotLocal",
    "CodeFailGeneric",
    # 原因码
    "ReasonLoginSessionNotFound",
    "ReasonProxyOffline",
    "ReasonAttemptConflict",
    "ReasonAttemptMismatch",
    "ReasonAttemptInactive",
    "ReasonAttemptIDRequired",
    "ReasonAttemptNotFound",
    "ReasonAttemptExpired",
    "ReasonCancelled",
    "ReasonWakeScanRequired",
    "ReasonSecurityReloginNeeded",
    "ReasonSessionInvalid",
    "ReasonWakeRequestFailed",
    "ReasonLoginRequestFailed",
    # 消息类型
    "MsgTypeText",
    "MsgTypeImage",
    "MsgTypeVoice",
    "MsgTypeCard",
    "MsgTypeVideo",
    "MsgTypeSticker",
    "MsgTypeLocation",
    "MsgTypeApp",
    "MsgTypeSystem",
    "MsgTypeRevoke",
    # 文件类型
    "FileTypeImage",
    "FileTypeVideo",
    "FileTypeFile",
]
