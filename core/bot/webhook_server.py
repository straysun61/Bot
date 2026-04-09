"""
Webhook服务模块
提供本地HTTP服务，接收外部推送的任务
"""
import asyncio
import logging
from typing import Callable, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from core.bot.models import TaskInstruction

logger = logging.getLogger(__name__)

# 创建路由
webhook_router = APIRouter(prefix="/webhook", tags=["Webhook"])


class TaskReceiveRequest(BaseModel):
    """任务接收请求"""
    task_id: str
    user_prompt: str = ""
    image_list: list[str] = []
    task_type: str = "general_chat"
    metadata: dict = {}


class TaskReceiveResponse(BaseModel):
    """任务接收响应"""
    status: str
    task_id: str
    message: str


class TaskCancelRequest(BaseModel):
    """任务取消请求"""
    task_id: str


# 任务处理器回调
_task_handler: Optional[Callable] = None


def set_task_handler(handler: Callable) -> None:
    """设置任务处理器"""
    global _task_handler
    _task_handler = handler


@webhook_router.post("/tasks", response_model=TaskReceiveResponse)
async def receive_task(
    request: TaskReceiveRequest,
    x_access_token: Optional[str] = Header(None, alias="X-Access-Token")
) -> TaskReceiveResponse:
    """
    接收推送的任务

    Args:
        request: 任务接收请求
        x_access_token: 访问令牌

    Returns:
        接收确认响应
    """
    from core.bot.config import get_config
    config = get_config()

    # 验证访问令牌
    if config.callback_token and x_access_token != config.callback_token:
        raise HTTPException(status_code=401, detail="Invalid access token")

    # 构建任务指令
    task = TaskInstruction(
        task_id=request.task_id,
        user_prompt=request.user_prompt,
        image_list=request.image_list,
        task_type=request.task_type,
        metadata=request.metadata
    )

    # 调用任务处理器
    if _task_handler:
        try:
            await _task_handler(task)
            logger.info(f"Task {task.task_id} received via webhook")
        except Exception as e:
            logger.error(f"Error handling task {task.task_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    else:
        logger.warning(f"No task handler configured, task {task.task_id} not processed")

    return TaskReceiveResponse(
        status="accepted",
        task_id=task.task_id,
        message="Task received and queued for processing"
    )


@webhook_router.post("/tasks/cancel/{task_id}", response_model=dict)
async def cancel_task(
    task_id: str,
    x_access_token: Optional[str] = Header(None, alias="X-Access-Token")
) -> dict:
    """
    取消指定任务

    Args:
        task_id: 任务ID
        x_access_token: 访问令牌

    Returns:
        取消结果
    """
    from core.bot.config import get_config
    config = get_config()

    # 验证访问令牌
    if config.callback_token and x_access_token != config.callback_token:
        raise HTTPException(status_code=401, detail="Invalid access token")

    # TODO: 实现任务取消逻辑
    return {"status": "cancelled", "task_id": task_id}


@webhook_router.get("/tasks/next", response_model=TaskReceiveResponse)
async def get_next_task(
    x_access_token: Optional[str] = Header(None, alias="X-Access-Token")
) -> TaskReceiveResponse:
    """
    主动获取下一个待处理任务（轮询模式）

    Returns:
        下一个任务
    """
    from core.bot.config import get_config
    config = get_config()

    # 验证访问令牌
    if config.callback_token and x_access_token != config.callback_token:
        raise HTTPException(status_code=401, detail="Invalid access token")

    # TODO: 从队列获取下一个任务
    raise HTTPException(status_code=501, detail="Not implemented yet")
