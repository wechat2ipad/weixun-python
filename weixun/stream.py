"""WebSocket 实时消息流。

协议端实测约束：
  - 鉴权只有 query 参数 key
  - 同一 key 只允许一条连接，新连接会**顶掉**旧连接
  - 断线期间消息**不补发**
  - 服务端每 60 秒发 ping，读超时 300 秒
  - 客户端发 "ping" 回 "pong"，发 "sync" 回 "sync completed"
  - 帧结构 {key, message, type}；内部字符串包在 {"str": ...}
  - 另有 type=record_content 的结构化事件
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

if TYPE_CHECKING:
    from .client import Client


@dataclass
class Message:
    """从流里解析出来的一条微信消息。"""

    msg_id: int = 0
    new_msg_id: str = ""
    """64 位消息 ID，字符串形式（超过 2^53）"""
    from_user: str = ""
    to_user: str = ""
    msg_type: int = 0
    content: str = ""
    create_time: int = 0
    push_content: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_group(self) -> bool:
        return self.from_user.endswith("@chatroom")


@dataclass
class RecordContentEvent:
    """type=record_content 事件（大聊天记录补拉完成后推送）。"""

    message_id: str = ""
    talker: str = ""
    success: bool = False
    content: str = ""
    length: int = 0
    timestamp: int = 0
    error: str = ""


@dataclass
class StreamOptions:
    on_message: Optional[Callable[[Message], None]] = None
    on_record_content: Optional[Callable[[RecordContentEvent], None]] = None
    on_error: Optional[Callable[[Exception], None]] = None
    on_state_change: Optional[Callable[[str], None]] = None
    max_backoff: float = 60.0


class Stream:
    """WebSocket 消息流（后台线程 + 自动重连）。"""

    def __init__(self, client: "Client", options: Optional[StreamOptions] = None) -> None:
        self._c = client
        self.options = options or StreamOptions()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "Stream":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def __enter__(self) -> "Stream":
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.stop()

    # ── 内部 ─────────────────────────────────────────

    def _ws_url(self) -> str:
        base = self._c.base_url
        if base.startswith("https://"):
            base = "wss://" + base[len("https://"):]
        elif base.startswith("http://"):
            base = "ws://" + base[len("http://"):]
        return f"{base.rstrip('/')}/ws/GetSyncMsg?key={self._c._key}"

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            self._state("connecting")
            try:
                self._connect_once()
            except Exception as exc:  # noqa: BLE001
                self._error(exc)
            if self._stop.is_set():
                return
            self._state("reconnecting")
            self._stop.wait(backoff)
            backoff = min(backoff * 2, self.options.max_backoff)

    def _connect_once(self) -> None:
        try:
            import websocket  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "WebSocket 支持需要安装 websocket-client：pip install websocket-client"
            ) from exc

        ws = websocket.create_connection(self._ws_url(), timeout=30)
        self._state("connected")
        try:
            while not self._stop.is_set():
                raw = ws.recv()
                if not raw:
                    continue
                self._handle_frame(raw)
        finally:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass

    def _handle_frame(self, raw: Any) -> None:
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                return
        text = str(raw).strip()
        if text in ("pong", "ping", "sync completed") or not text.startswith("{"):
            return
        try:
            frame = json.loads(text)
        except json.JSONDecodeError as exc:
            self._error(exc)
            return

        ftype = frame.get("type")
        if ftype == "message":
            msg = parse_add_msg(frame.get("message") or {})
            if msg is not None and self.options.on_message:
                self.options.on_message(msg)
        elif ftype == "record_content":
            ev = RecordContentEvent(
                message_id=str(frame.get("message_id") or ""),
                talker=frame.get("talker") or "",
                success=bool(frame.get("success")),
                content=frame.get("content") or "",
                length=int(frame.get("length") or 0),
                timestamp=int(frame.get("timestamp") or 0),
                error=frame.get("error") or "",
            )
            if self.options.on_record_content:
                self.options.on_record_content(ev)

    def _state(self, s: str) -> None:
        if self.options.on_state_change:
            try:
                self.options.on_state_change(s)
            except Exception:  # noqa: BLE001
                pass

    def _error(self, exc: Exception) -> None:
        if self.options.on_error:
            try:
                self.options.on_error(exc)
            except Exception:  # noqa: BLE001
                pass


def unwrap_string(v: Any) -> str:
    """处理协议端两种字符串表达：对象 {"str": "xxx"} 或裸字符串 "xxx"。"""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return str(v.get("str") or "")
    return ""


def parse_add_msg(node: Dict[str, Any]) -> Optional[Message]:
    """解析 message 节点。"""
    if not isinstance(node, dict):
        return None
    new_msg_id = node.get("new_msg_id")
    if isinstance(new_msg_id, bool):
        new_msg_id = ""
    elif isinstance(new_msg_id, int):
        new_msg_id = str(new_msg_id)
    else:
        new_msg_id = str(new_msg_id or "")

    return Message(
        msg_id=int(node.get("msg_id") or 0),
        new_msg_id=new_msg_id,
        from_user=unwrap_string(node.get("from_user_name")),
        to_user=unwrap_string(node.get("to_user_name")),
        msg_type=int(node.get("msg_type") or 0),
        content=unwrap_string(node.get("content")),
        create_time=int(node.get("create_time") or 0),
        push_content=str(node.get("push_content") or ""),
        raw=node,
    )
