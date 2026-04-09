"""
速率限制模块
基于滑动窗口的全局速率控制
"""
import time
from collections import deque
from threading import Lock

from core.bot.config import get_config


class RateLimiter:
    """滑动窗口速率限制器"""

    def __init__(self, max_requests: int, window_seconds: int = 3600):
        """
        初始化速率限制器

        Args:
            max_requests: 时间窗口内最大请求数
            window_seconds: 时间窗口大小（秒），默认1小时
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: deque = deque()
        self._lock = Lock()

    def is_allowed(self) -> bool:
        """检查是否允许请求"""
        with self._lock:
            now = time.time()

            # 清理过期的请求记录
            while self.requests and self.requests[0] < now - self.window_seconds:
                self.requests.popleft()

            # 检查是否超过限制
            return len(self.requests) < self.max_requests

    def record_request(self) -> None:
        """记录一次请求"""
        with self._lock:
            self.requests.append(time.time())

    def get_remaining(self) -> int:
        """获取剩余可用请求次数"""
        with self._lock:
            now = time.time()

            # 清理过期的请求记录
            while self.requests and self.requests[0] < now - self.window_seconds:
                self.requests.popleft()

            return max(0, self.max_requests - len(self.requests))

    def get_usage(self) -> dict:
        """获取当前使用情况"""
        with self._lock:
            now = time.time()

            # 清理过期的请求记录
            while self.requests and self.requests[0] < now - self.window_seconds:
                self.requests.popleft()

            return {
                "used": len(self.requests),
                "limit": self.max_requests,
                "remaining": max(0, self.max_requests - len(self.requests)),
                "window_seconds": self.window_seconds
            }


# 基于配置的全局速率限制器
_rate_limiter: RateLimiter = None


def get_rate_limiter() -> RateLimiter:
    """获取全局速率限制器（单例）"""
    global _rate_limiter
    if _rate_limiter is None:
        config = get_config()
        _rate_limiter = RateLimiter(max_requests=config.rate_limit)
    return _rate_limiter
