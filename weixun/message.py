"""消息服务：发送、群发、撤回，以及逐条结果归一化。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .client import Client

# 协议端 msg_type 取值
MsgTypeText = 1
MsgTypeImage = 3
MsgTypeVoice = 34
MsgTypeCard = 42
MsgTypeVideo = 43
MsgTypeSticker = 47
MsgTypeLocation = 48
MsgTypeApp = 49
MsgTypeSystem = 10000  # 含联系人同步事件
MsgTypeRevoke = 10002

# 逐条结果里的成功标志字段（协议端实测有 7 种命名）
_SUCCESS_FLAGS = (
    "isSendSuccess",
    "isCommentSuccess",
    "isMarkSuccess",
    "isHideSuccess",
    "isFollowSuccess",
    "isUploadSuccess",
    "isSuccess",
)
# 接收方字段的两种拼写
_TO_KEYS = ("toUSerName", "toUserName", "to_user_name")
# 错误字段（errMgs 是 UploadFriendCircleImage 的拼写错误）
_ERROR_KEYS = ("errMsg", "errMgs", "error")


@dataclass
class SendTextRequest:
    """发送文本消息的请求。"""

    to: str
    """接收方 wxid（个人）或 xxx@chatroom（群）。"""

    text: str
    """消息内容。"""

    at: Optional[List[str]] = None
    """需要 @ 的成员 wxid 列表。"""


@dataclass
class SendTextResult:
    """单条发送的结果（已归一化协议端的字段差异）。"""

    ok: bool
    """该条是否发送成功。"""

    to: str = ""
    """接收方。"""

    error_message: str = ""
    """失败原因（成功时为空）。"""

    raw: Dict[str, Any] = field(default_factory=dict)
    """协议端原始返回。"""


class MessageService:
    """封装 /message/* 接口。"""

    def __init__(self, client: "Client") -> None:
        self._c = client

    # ── 发送 ─────────────────────────────────────────

    def send_text(self, req: SendTextRequest) -> SendTextResult:
        """发送一条文本消息。

        协议端要求请求体是 ``{"MsgItem": [ {...} ]}``，MsgItem 是**数组**。
        """
        results = self.send_text_batch([req])
        if not results:
            raise ValueError("协议端未返回发送结果")
        return results[0]

    def send_text_batch(self, reqs: List[SendTextRequest]) -> List[SendTextResult]:
        """批量发送文本消息。

        协议端内部会在多条之间随机 sleep 1~3 秒（messageService.go:868），
        SDK 不重复节流，但整体仍受 RateLimiter 约束。
        """
        if not reqs:
            raise ValueError("至少需要一条消息")
        items = []
        for r in reqs:
            if not r.to:
                raise ValueError("接收方不能为空")
            item: Dict[str, Any] = {
                "ToUserName": r.to,
                "TextContent": r.text,
                "MsgType": 1,
            }
            if r.at:
                item["AtWxIDList"] = r.at
            items.append(item)
        data = self._c._call("POST", "/message/SendTextMessage", {"MsgItem": items})
        return parse_batch_results(data)

    def send_image(self, to: str, image_base64: str) -> SendTextResult:
        """发送图片（base64，可带 data URI 前缀）。"""
        body = {
            "MsgItem": [
                {"ToUserName": to, "ImageContent": image_base64, "MsgType": 2}
            ]
        }
        data = self._c._call("POST", "/message/SendImageMessage", body)
        results = parse_batch_results(data)
        if not results:
            raise ValueError("协议端未返回发送结果")
        return results[0]

    def group_mass_text(self, to: List[str], content: str) -> Any:
        """向多个群/联系人批量发送相同文本。

        注意：协议端返回微信 MassSendResponse 原样透传，
        **没有**收件人级别的成功/失败明细，只能看顶层 baseResponse.ret。
        """
        if not to:
            raise ValueError("收件人列表不能为空")
        return self._c._call(
            "POST", "/message/GroupMassMsgText", {"ToUserName": to, "Content": content}
        )

    def revoke(self, to: str, new_msg_id: str, client_msg_id: str) -> None:
        """撤回消息。new_msg_id 必须是字符串形式（64 位）。"""
        self._c._call(
            "POST",
            "/message/RevokeMsg",
            {
                "ToUserName": to,
                "NewMsgId": new_msg_id,
                "ClientMsgId": client_msg_id,
            },
        )

    def mark_all_read(self, to: str) -> None:
        """标记会话已读。"""
        self._c._call("POST", "/message/MarkAllMessagesAsRead", {"ToUserName": to})

    # ── 回调 ─────────────────────────────────────────

    def set_callback(self, callback_url: str) -> None:
        """设置 HTTP 消息回调地址（5 秒超时、不重试）。"""
        self._c._call("POST", "/message/SetCallback", {"CallbackUrl": callback_url})


def parse_batch_results(data: Any) -> List[SendTextResult]:
    """把协议端五花八门的逐条结果统一成 SendTextResult。"""
    if data is None:
        return []
    items: List[Dict[str, Any]]
    if isinstance(data, list):
        items = [x for x in data if isinstance(x, dict)]
    elif isinstance(data, dict):
        items = [data]
    else:
        return []

    out: List[SendTextResult] = []
    for item in items:
        to = next(
            (str(item[k]) for k in _TO_KEYS if isinstance(item.get(k), str) and item[k]),
            "",
        )
        err = next(
            (str(item[k]) for k in _ERROR_KEYS if isinstance(item.get(k), str) and item[k]),
            "",
        )
        has_flag = any(f in item for f in _SUCCESS_FLAGS)
        if has_flag:
            ok = any(item.get(f) is True for f in _SUCCESS_FLAGS)
        else:
            ok = True
        if err:
            ok = False
        out.append(SendTextResult(ok=ok, to=to, error_message=err, raw=item))
    return out


def is_contact_sync(msg_type: int) -> bool:
    """是否为联系人同步事件。

    协议端把联系人事件塞进伪造的 msg_type=10000 消息里，
    且它的 new_msg_id 是无意义的伪造值，不要用它做去重。
    """
    return msg_type == MsgTypeSystem


def is_revoke(msg_type: int) -> bool:
    """是否为撤回通知。"""
    return msg_type == MsgTypeRevoke
