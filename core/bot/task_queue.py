"""
任务队列管理模块
负责任务的接收、状态管理、执行调度
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Optional

from core.bot.models import TaskInstruction, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class TaskQueue:
    """任务队列管理器"""

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._tasks: dict[str, TaskResult] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._executing: bool = False

    async def put(self, task: TaskInstruction) -> None:
        """将任务加入队列"""
        # 初始化任务状态
        self._tasks[task.task_id] = TaskResult(
            task_id=task.task_id,
            status=TaskStatus.PENDING
        )
        await self._queue.put(task)
        logger.info(f"Task {task.task_id} added to queue")

    async def get(self) -> TaskInstruction:
        """从队列获取任务（阻塞）"""
        task = await self._queue.get()
        return task

    def get_task_status(self, task_id: str) -> Optional[TaskResult]:
        """获取任务状态"""
        return self._tasks.get(task_id)

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: Any = None,
        error: str = None,
        completed_at: datetime = None
    ) -> None:
        """更新任务状态"""
        if task_id in self._tasks:
            task_result = self._tasks[task_id]
            task_result.status = status
            if result is not None:
                task_result.result = result
            if error is not None:
                task_result.error = error
            if completed_at is not None:
                task_result.completed_at = completed_at
            elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.TIMEOUT):
                task_result.completed_at = datetime.utcnow()

    def get_pending_tasks(self) -> list[TaskResult]:
        """获取所有待处理任务"""
        return [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]

    def get_running_tasks(self) -> list[TaskResult]:
        """获取所有运行中任务"""
        return [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]

    def get_completed_tasks(self) -> list[TaskResult]:
        """获取所有已完成任务"""
        return [t for t in self._tasks.values() if t.status == TaskStatus.COMPLETED]

    def task_done(self, task_id: str) -> None:
        """标记任务完成"""
        self._queue.task_done()

    @property
    def queue_size(self) -> int:
        """获取队列大小"""
        return self._queue.qsize()

    @property
    def total_tasks(self) -> int:
        """获取总任务数"""
        return len(self._tasks)


# 全局队列实例
_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    """获取任务队列单例"""
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue
