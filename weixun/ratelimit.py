"""限速器：令牌桶 + 最小间隔。

为什么 SDK 必须自带限速：协议端实测没有任何服务端限流
（全仓无 token bucket、无 429、业务执行在锁外）。
客户如果并发猛发，不会收到 API 错误，而是直接被微信风控。

默认值来自官方风控建议：
  - 单账号 40 条/分钟
  - 切换不同用户间隔 ≥1s
  - 切换不同群 2~5s
"""

from __future__ import annotations

import threading
import time
from typing import Optional


class RateLimiter:
    """线程安全的令牌桶限速器。"""

    def __init__(self, capacity: int, per_window: float) -> None:
        """capacity 次请求 / per_window 秒。"""
        if capacity <= 0:
            raise ValueError("capacity 必须大于 0")
        self.capacity = capacity
        self.interval = per_window / capacity
        self.tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """阻塞直到获取一个令牌。timeout 为 None 表示无限等待。"""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last
                self.tokens = min(self.capacity, self.tokens + elapsed / self.interval)
                self._last = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
                need = (1 - self.tokens) * self.interval

            if deadline is not None:
                remain = deadline - time.monotonic()
                if remain <= 0:
                    return False
                need = min(need, remain)
            time.sleep(max(need, 0.001))


class Throttle:
    """强制两次调用之间的最小间隔，用于「切换不同用户 ≥1s」这类约束。"""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            elapsed = time.monotonic() - self._last
            self._last = time.monotonic()
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
