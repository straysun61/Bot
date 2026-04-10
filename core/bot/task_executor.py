"""
任务执行器模块
负责任务的执行、超时处理、结果回调
"""
import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional

from core.bot.callback_handler import CallbackHandler, get_callback_handler
from core.bot.config import ComputeTier, get_config
from core.bot.tier_manager import get_tier_manager
from core.bot.models import TaskInstruction, TaskResult, TaskStatus
from core.bot.rate_limiter import get_rate_limiter
from core.bot.task_queue import TaskQueue, get_task_queue

logger = logging.getLogger(__name__)


class TaskExecutor:
    """任务执行器"""

    def __init__(
        self,
        queue: Optional[TaskQueue] = None,
        callback_handler: Optional[CallbackHandler] = None
    ):
        self.queue = queue or get_task_queue()
        self.callback_handler = callback_handler or get_callback_handler()
        self.config = get_config()
        self.tier_manager = get_tier_manager()
        self.rate_limiter = get_rate_limiter()

        self._running = False
        self._workers: list[asyncio.Task] = []

    async def start(self) -> None:
        """启动执行器"""
        if self._running:
            return
        self._running = True
        logger.info("TaskExecutor started")

    async def stop(self) -> None:
        """停止执行器"""
        self._running = False
        for worker in self._workers:
            worker.cancel()
        self._workers.clear()
        logger.info("TaskExecutor stopped")

    def start_workers(self, num_workers: int = 2) -> None:
        """启动工作线程"""
        for i in range(num_workers):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)
            logger.info(f"Worker {i} started")

    async def submit_task(
        self,
        task: TaskInstruction,
        callback_url: Optional[str] = None
    ) -> str:
        """
        提交任务到执行器

        Args:
            task: 任务指令
            callback_url: 回调地址

        Returns:
            任务ID
        """
        # 检查速率限制
        if not self.rate_limiter.is_allowed():
            raise RuntimeError("Rate limit exceeded")

        # 记录请求
        self.rate_limiter.record_request()

        # 优先使用动态 callback_url（SSE 下发），其次使用传入参数
        effective_callback_url = task.callback_url or callback_url
        if effective_callback_url:
            task.metadata["callback_url"] = effective_callback_url

        # 加入队列
        await self.queue.put(task)
        return task.task_id

    async def _worker(self, worker_id: int) -> None:
        """工作线程"""
        logger.info(f"Worker {worker_id} started")

        while self._running:
            try:
                # 从队列获取任务（带超时）
                try:
                    task = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # 执行任务
                await self._execute_task(task, worker_id)

                # 标记任务完成
                self.queue.task_done(task.task_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")

        logger.info(f"Worker {worker_id} stopped")

    async def _execute_task(self, task: TaskInstruction, worker_id: int) -> None:
        """执行单个任务"""
        task_id = task.task_id
        started_at = datetime.utcnow()

        # 更新状态为运行中
        self.queue.update_task_status(task_id, TaskStatus.RUNNING, started_at=started_at)

        try:
            # 任务执行（由子类或外部处理函数实现）
            result = await self._run_task_handler(task)

            # 更新完成状态
            self.queue.update_task_status(
                task_id,
                TaskStatus.COMPLETED,
                result=result,
                completed_at=datetime.utcnow()
            )

            logger.info(f"Task {task_id} completed by worker {worker_id}")

        except asyncio.CancelledError:
            self.queue.update_task_status(task_id, TaskStatus.CANCELLED, error="Task cancelled")
            raise

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            self.queue.update_task_status(
                task_id,
                TaskStatus.FAILED,
                error=str(e),
                completed_at=datetime.utcnow()
            )

        finally:
            # 触发回调
            await self._trigger_callback(task_id)

    async def _run_task_handler(self, task: TaskInstruction) -> any:
        """
        运行任务处理函数
        先下载外部资源，再调用 SkillExecutor 自动分发到对应技能
        """
        from core.bot.skill_executor import get_skill_executor
        from core.image_handler import ImageHandler

        # 1. 预处理：下载外部带签名的各类图片（如 Minio URL）
        if task.image_list:
            remote_urls = [url for url in task.image_list if url.startswith("http")]
            if remote_urls:
                handler = ImageHandler(doc_id=task.task_id)
                downloaded_images = await handler.download_images_from_urls(remote_urls)
                
                # 替换原始 URL 为本地路径
                new_image_list = []
                down_idx = 0
                for url in task.image_list:
                    if url.startswith("http"):
                        if down_idx < len(downloaded_images):
                            new_image_list.append(downloaded_images[down_idx].stored_path)
                            down_idx += 1
                        else:
                            # 下载失败，丢弃或保留原样均可，这里保留原样
                            new_image_list.append(url)
                    else:
                        new_image_list.append(url)
                task.image_list = new_image_list

        # 2. 调用具体的业务技能分发器
        skill_executor = get_skill_executor()
        return await skill_executor.execute_task(task)

    async def _trigger_callback(self, task_id: str) -> None:
        """触发任务回调"""
        result = self.queue.get_task_status(task_id)
        if not result:
            return

        callback_url = result.metadata.get("callback_url")
        access_token = result.metadata.get("access_token")
        await self.callback_handler.send_completion_callback(
            result, callback_url, access_token
        )

    async def _handle_timeout(self, task_id: str, timeout_seconds: int) -> None:
        """处理任务超时"""
        try:
            await asyncio.sleep(timeout_seconds)

            result = self.queue.get_task_status(task_id)
            if result and result.status == TaskStatus.RUNNING:
                self.queue.update_task_status(
                    task_id,
                    TaskStatus.TIMEOUT,
                    error=f"Task timeout after {timeout_seconds} seconds",
                    completed_at=datetime.utcnow()
                )

                logger.warning(f"Task {task_id} timed out")
                callback_url = result.metadata.get("callback_url")
                access_token = result.metadata.get("access_token")
                await self.callback_handler.send_timeout_callback(
                    task_id, callback_url, access_token
                )

        except asyncio.CancelledError:
            pass


# 全局实例
_task_executor: Optional[TaskExecutor] = None


def get_task_executor() -> TaskExecutor:
    """获取任务执行器单例"""
    global _task_executor
    if _task_executor is None:
        _task_executor = TaskExecutor()
    return _task_executor
