"""
SSE客户端模块
连接外部SSE服务，实时接收任务推送
"""
import asyncio
import json
import logging
from typing import Callable, Optional

import httpx

from core.bot.models import TaskInstruction

logger = logging.getLogger(__name__)


class SSEClient:
    """SSE任务接收客户端"""

    def __init__(
        self,
        endpoint: str,
        token: str = None,
        on_task_received: Optional[Callable] = None
    ):
        """
        初始化SSE客户端

        Args:
            endpoint: SSE服务地址
            token: 访问令牌
            on_task_received: 任务接收回调函数
        """
        self.endpoint = endpoint
        self.token = token
        self.on_task_received = on_task_received
        self._running = False
        self._task = None

    async def start(self) -> None:
        """启动SSE连接"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._connect())
        logger.info(f"SSE client started, connecting to {self.endpoint}")

    async def stop(self) -> None:
        """停止SSE连接"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("SSE client stopped")

    async def _connect(self) -> None:
        """建立SSE连接并接收任务"""
        headers = {"Accept": "text/event-stream"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        while self._running:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    async with client.stream("GET", self.endpoint, headers=headers) as response:
                        if response.status_code != 200:
                            logger.warning(f"SSE connection failed with status {response.status_code}")
                            await asyncio.sleep(5)
                            continue

                        async for line in response.aiter_lines():
                            if not self._running:
                                break

                            if line.startswith("data:"):
                                data = line[5:].strip()
                                if data:
                                    await self._handle_event(data)

            except asyncio.CancelledError:
                break
            except httpx.RequestError as e:
                logger.error(f"SSE connection error: {e}")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"SSE unexpected error: {e}")
                await asyncio.sleep(5)

    async def _handle_event(self, data: str) -> None:
        """处理接收到的SSE事件"""
        try:
            event_data = json.loads(data)
            logger.info(f"SSE received event: {event_data.get('event', 'unknown')}")

            event_type = event_data.get("event", "")

            if event_type == "task" or "task_id" in event_data:
                task = TaskInstruction(
                    task_id=event_data.get("task_id", ""),
                    user_prompt=event_data.get("user_prompt", ""),
                    image_list=event_data.get("image_list", []),
                    task_type=event_data.get("task_type", "general_chat"),
                    metadata=event_data.get("metadata", {})
                )

                if self.on_task_received:
                    await self.on_task_received(task)

            elif event_type == "ping":
                logger.debug("SSE ping received")

        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in SSE event: {data}")
        except Exception as e:
            logger.error(f"Error handling SSE event: {e}")


# SSE客户端实例管理
_sse_client: Optional[SSEClient] = None


def get_sse_client() -> Optional[SSEClient]:
    """获取SSE客户端"""
    return _sse_client


def create_sse_client(
    endpoint: str,
    token: str = None,
    on_task_received: Callable = None
) -> SSEClient:
    """创建并返回SSE客户端"""
    global _sse_client
    _sse_client = SSEClient(
        endpoint=endpoint,
        token=token,
        on_task_received=on_task_received
    )
    return _sse_client
