"""
Bot API路由
提供任务提交、状态查询、技能管理、配置查询等接口
"""
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.bot import (
    ComputeTier,
    TaskInstruction,
    TaskStatus,
    get_config,
    get_task_executor,
    get_task_queue,
    get_rate_limiter,
    get_tier_manager,
    get_skill_executor,
)

router = APIRouter(prefix="/api/v1/bot", tags=["Bot"])


class SubmitTaskRequest(BaseModel):
    """提交任务请求"""
    user_prompt: str = ""
    image_list: list[str] = []
    task_type: str = "general_chat"
    metadata: dict = {}
    callback_url: Optional[str] = None


class SubmitTaskResponse(BaseModel):
    """提交任务响应"""
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: TaskStatus
    result: Optional[dict] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class RateLimitStatus(BaseModel):
    """速率限制状态"""
    used: int
    limit: int
    remaining: int


class TierInfo(BaseModel):
    """算力层级信息"""
    tier: str
    type: str
    model: str


class SkillInfo(BaseModel):
    """技能信息"""
    name: str
    description: str
    parameters: dict


@router.post("/tasks", response_model=SubmitTaskResponse)
async def submit_task(request: SubmitTaskRequest) -> SubmitTaskResponse:
    """提交新任务"""
    task_id = str(uuid.uuid4())

    task = TaskInstruction(
        task_id=task_id,
        user_prompt=request.user_prompt,
        image_list=request.image_list,
        task_type=request.task_type,
        metadata=request.metadata
    )

    executor = get_task_executor()

    try:
        await executor.submit_task(task, request.callback_url)
        return SubmitTaskResponse(
            task_id=task_id,
            status="pending",
            message="Task submitted successfully"
        )
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e))


@router.get("/tasks/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """获取任务状态"""
    queue = get_task_queue()
    result = queue.get_task_status(task_id)

    if not result:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskStatusResponse(
        task_id=result.task_id,
        status=result.status,
        result=result.result,
        error=result.error,
        started_at=result.started_at.isoformat() if result.started_at else None,
        completed_at=result.completed_at.isoformat() if result.completed_at else None
    )


@router.get("/rate-limit", response_model=RateLimitStatus)
async def get_rate_limit_status() -> RateLimitStatus:
    """获取速率限制状态"""
    limiter = get_rate_limiter()
    usage = limiter.get_usage()
    return RateLimitStatus(**usage)


@router.get("/tiers", response_model=list[TierInfo])
async def list_tiers() -> list[TierInfo]:
    """列出所有算力层级配置"""
    tier_manager = get_tier_manager()
    tiers = []

    for tier in ComputeTier:
        cfg = tier_manager.get_tier_config(tier)
        tiers.append(TierInfo(
            tier=tier.value,
            type=cfg["type"].value,
            model=cfg["model"]
        ))

    return tiers


@router.get("/skills", response_model=list[SkillInfo])
async def list_skills() -> list[SkillInfo]:
    """列出所有可用技能"""
    executor = get_skill_executor()
    skills = executor.get_available_skills()
    return [SkillInfo(
        name=s.name,
        description=s.description,
        parameters=s.parameters
    ) for s in skills]


@router.get("/config")
async def get_config_info() -> dict:
    """获取当前配置信息"""
    config = get_config()
    return {
        "rate_limit": config.rate_limit,
        "callback_url": config.callback_url,
        "timeout_seconds": config.timeout_seconds,
        "receiver_mode": config.receiver_mode
    }


@router.post("/skills/execute")
async def execute_skill(
    skill_name: str,
    user_prompt: str = "",
    metadata: dict = {}
) -> dict:
    """
    直接执行技能（不经过任务队列）

    Args:
        skill_name: 技能名称
        user_prompt: 用户输入
        metadata: 额外元数据

    Returns:
        执行结果
    """
    from core.bot.skill import SkillContext, SkillRegistry

    task_id = str(uuid.uuid4())
    context = SkillContext(
        task_id=task_id,
        task_type=skill_name,
        user_prompt=user_prompt,
        metadata=metadata
    )

    result = await SkillRegistry.execute(skill_name, context)
    return {
        "success": result.success,
        "result": result.result,
        "error": result.error
    }
