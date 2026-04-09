"""
重试机制与超时处理模块
"""
import asyncio
import functools
import logging
from datetime import datetime
from typing import Any, Callable, Optional, TypeVar

from core.bot.config import get_config

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryConfig:
    """重试配置"""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base


class TimeoutError(Exception):
    """超时异常"""
    pass


class RetryError(Exception):
    """重试耗尽异常"""

    def __init__(self, message: str, last_error: Exception = None):
        super().__init__(message)
        self.last_error = last_error


def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    retry_on: tuple = (Exception,)
):
    """
    异步重试装饰器

    Args:
        max_attempts: 最大尝试次数
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟（秒）
        exponential_base: 指数基数
        retry_on: 需要重试的异常类型

    Usage:
        @async_retry(max_attempts=3)
        async def my_function():
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except retry_on as e:
                    last_error = e
                    if attempt == max_attempts:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise RetryError(
                            f"Failed after {max_attempts} attempts: {e}",
                            last_error=e
                        )

                    delay = min(base_delay * (exponential_base ** (attempt - 1)), max_delay)
                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)

            raise RetryError(f"Failed after {max_attempts} attempts", last_error)

        return wrapper
    return decorator


def async_timeout(seconds: float):
    """
    异步超时装饰器

    Args:
        seconds: 超时时间（秒）

    Usage:
        @async_timeout(30.0)
        async def my_function():
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                raise TimeoutError(f"{func.__name__} timed out after {seconds}s")

        return wrapper
    return decorator


class TaskTimeoutTracker:
    """
    任务超时追踪器

    用于追踪长时间运行的任务，自动标记超时
    """

    def __init__(self, timeout_seconds: int = 600):
        self.timeout_seconds = timeout_seconds
        self._tasks: dict[str, asyncio.Task] = {}
        self._start_times: dict[str, float] = {}

    def start_tracking(self, task_id: str, task: asyncio.Task) -> None:
        """开始追踪任务"""
        self._tasks[task_id] = task
        self._start_times[task_id] = asyncio.get_event_loop().time()

    def stop_tracking(self, task_id: str) -> None:
        """停止追踪任务"""
        if task_id in self._tasks:
            del self._tasks[task_id]
        if task_id in self._start_times:
            del self._start_times[task_id]

    def is_running(self, task_id: str) -> bool:
        """检查任务是否还在运行"""
        if task_id not in self._tasks:
            return False

        task = self._tasks[task_id]
        if task.done():
            self.stop_tracking(task_id)
            return False

        # 检查是否超时
        if task_id in self._start_times:
            elapsed = asyncio.get_event_loop().time() - self._start_times[task_id]
            if elapsed > self.timeout_seconds:
                logger.warning(f"Task {task_id} timed out after {elapsed:.1f}s")
                task.cancel()
                self.stop_tracking(task_id)
                return False

        return True

    def get_status(self, task_id: str) -> dict:
        """获取任务状态"""
        if task_id not in self._tasks:
            return {"status": "not_found"}

        task = self._tasks[task_id]
        if task.done():
            self.stop_tracking(task_id)
            try:
                result = task.result()
                return {"status": "completed", "result": result}
            except Exception as e:
                return {"status": "failed", "error": str(e)}

        elapsed = asyncio.get_event_loop().time() - self._start_times.get(task_id, 0)
        return {
            "status": "running",
            "elapsed_seconds": elapsed,
            "timeout_seconds": self.timeout_seconds
        }


# 从 task_status_manager 导入 TaskStatusManager
# 保持向后兼容
from core.bot.task_status_manager import TaskStatusManager, get_task_status_manager

__all__ = [
    'RetryConfig',
    'TimeoutError',
    'RetryError',
    'async_retry',
    'async_timeout',
    'TaskTimeoutTracker',
    'TaskStatusManager',
    'get_task_status_manager',
]
