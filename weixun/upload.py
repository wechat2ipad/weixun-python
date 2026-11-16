"""上传：multipart 大文件 + base64 辅助。

协议端实测只有**一个** multipart 接口：POST /message/CdnBigFileUpload
其余"上传"全部是 JSON + base64。
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import uuid
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from .client import Client

FileTypeImage = 2
FileTypeVideo = 4
FileTypeFile = 5
FileTypeMini = 6
FileTypeBig = 7
FileTypeOneG = 9
FileTypeVoice = 11


class UploadService:
    """封装上传能力。"""

    def __init__(self, client: "Client") -> None:
        self._c = client

    # ── multipart ────────────────────────────────────

    def big_file(
        self,
        file_path: str,
        *,
        file_type: int = FileTypeFile,
        to_user: str = "",
        thumb_path: str = "",
        aes_key_hex: str = "",
    ) -> Any:
        """上传大文件（multipart/form-data，≤200MB）。"""
        if not os.path.isfile(file_path):
            raise ValueError(f"文件不存在: {file_path}")
        size = os.path.getsize(file_path)
        if size > 200 * 1024 * 1024:
            raise ValueError("文件超过 200MB 上限")

        boundary = "----WeixunBoundary" + uuid.uuid4().hex
        parts: List[bytes] = []

        def add_field(name: str, value: str) -> None:
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
            )

        def add_file(name: str, path: str) -> None:
            filename = os.path.basename(path)
            ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: {ctype}\r\n\r\n".encode()
            )
            with open(path, "rb") as fh:
                parts.append(fh.read())
            parts.append(b"\r\n")

        add_file("file", file_path)
        if thumb_path and os.path.isfile(thumb_path):
            add_file("thumb", thumb_path)
        add_field("fileType", str(file_type or FileTypeFile))
        if to_user:
            add_field("toUser", to_user)
        if aes_key_hex:
            add_field("aesKeyHex", aes_key_hex)
        parts.append(f"--{boundary}--\r\n".encode())

        payload = b"".join(parts)
        url = f"{self._c.base_url}/message/CdnBigFileUpload?key={self._c._key}"

        import urllib.request as ureq

        req = ureq.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": self._c.options.user_agent,
            },
        )
        return self._c._read_envelope(ureq.urlopen(req, timeout=self._c.options.timeout))

    # ── base64 辅助 ──────────────────────────────────

    @staticmethod
    def base64_from_file(path: str) -> str:
        with open(path, "rb") as fh:
            return base64.b64encode(fh.read()).decode()

    @staticmethod
    def base64_from_bytes(b: bytes) -> str:
        return base64.b64encode(b).decode()

    @staticmethod
    def image_data_uri(mime: str, b: bytes) -> str:
        """生成协议端可直接接受的 data URI（协议端会按逗号切分取最后一段）。"""
        mime = mime or "image/png"
        return f"data:{mime};base64,{base64.b64encode(b).decode()}"

    @staticmethod
    def strip_data_uri(v: str) -> str:
        """去掉 data URI 前缀，只留纯 base64。"""
        if v.startswith("data:") and "," in v:
            return v.split(",", 1)[1]
        return v

    # ── JSON + base64 类接口 ─────────────────────────

    def upload_image_to_cdn(self, image_base64: str) -> Any:
        return self._c._call(
            "POST", "/message/UploadImageToCDN", {"imageContent": image_base64}
        )

    def upload_head_image(self, image_base64: str) -> None:
        self._c._call("POST", "/user/UploadHeadImage", {"Base64": image_base64})

    def send_voice(self, to: str, voice_base64: str, second: int) -> None:
        self._c._call(
            "POST",
            "/message/SendVoice",
            {"ToUserName": to, "VoiceData": voice_base64, "VoiceSecond": second},
        )
