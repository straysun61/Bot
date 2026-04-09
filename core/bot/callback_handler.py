"""
回调处理器模块
负责任务结果的回调通知，支持重试机制
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

import httpx

from core.bot.config import get_config
from core.bot.models import CallbackPayload, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class CallbackHandler:
    """任务回调处理器"""

    MAX_RETRIES = 3
    BASE_DELAY = 1.0
    MAX_DELAY = 30.0
    TIMEOUT = 60.0

    def __init__(self):
        self.config = get_config()

    async def send_callback(
        self,
        payload: CallbackPayload,
        callback_url: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> bool:
        """
        发送回调请求

        Args:
            payload: 回调载荷
            callback_url: 回调地址（可选）
            access_token: 访问令牌（可选）

        Returns:
            是否发送成功
        """
        url = callback_url or self.config.callback_url
        token = access_token or self.config.callback_token

        if not url:
            logger.warning(f"No callback URL configured for task {payload.task_id}")
            return False

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        payload_dict = payload.model_dump(mode="json")

        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                    response = await client.post(url, json=payload_dict, headers=headers)

                    if response.status_code in (200, 201, 202):
                        logger.info(f"Callback sent successfully for task {payload.task_id}")
                        return True

                    logger.warning(
                        f"Callback failed for task {payload.task_id}: "
                        f"status={response.status_code}, body={response.text}"
                    )

            except httpx.TimeoutException:
                logger.warning(
                    f"Callback timeout for task {payload.task_id} "
                    f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                )
            except httpx.RequestError as e:
                logger.warning(
                    f"Callback error for task {payload.task_id}: {e} "
                    f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                )

            if attempt < self.MAX_RETRIES - 1:
                delay = min(self.BASE_DELAY * (2 ** attempt), self.MAX_DELAY)
                await asyncio.sleep(delay)

        logger.error(f"Callback failed after {self.MAX_RETRIES} attempts for task {payload.task_id}")
        return False

    async def send_completion_callback(
        self,
        result: TaskResult,
        callback_url: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> bool:
        """发送任务完成回调"""
        payload = CallbackPayload(
            task_id=result.task_id,
            status=result.status,
            result=result.result,
            error=result.error,
            started_at=result.started_at,
            completed_at=result.completed_at,
            compute_tier=result.compute_tier,
            timestamp=datetime.utcnow()
        )
        return await self.send_callback(payload, callback_url, access_token)

    async def send_timeout_callback(
        self,
        task_id: str,
        callback_url: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> bool:
        """发送任务超时回调"""
        payload = CallbackPayload(
            task_id=task_id,
            status=TaskStatus.TIMEOUT,
            error=f"Task execution timeout after {self.config.timeout_seconds} seconds",
            completed_at=datetime.utcnow(),
            timestamp=datetime.utcnow()
        )
        return await self.send_callback(payload, callback_url, access_token)


# 全局实例
_callback_handler: Optional[CallbackHandler] = None


def get_callback_handler() -> CallbackHandler:
    """获取回调处理器单例"""
    global _callback_handler
    if _callback_handler is None:
        _callback_handler = CallbackHandler()
    return _callback_handler
