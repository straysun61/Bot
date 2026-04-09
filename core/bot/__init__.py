"""
机器人统一架构 - 核心模块
阶段1: 基础配置与核心框架
阶段2: 任务获取与调度机制
阶段3: 标准化任务指令解析与分发
阶段4: 内置工具Skills集成
"""

# ============ 阶段1: 配置管理 ============
from core.bot.config import (
    APIProviderType,
    BotSettings,
    ComputeTier,
    ConfigManager,
    TierConfig,
    get_config,
    get_settings,
)

# ============ 阶段1: 速率限制 ============
from core.bot.rate_limiter import (
    RateLimiter,
    get_rate_limiter,
)

# ============ 阶段1: 算力管理 ============
from core.bot.tier_manager import (
    TierManager,
    get_tier_manager,
)

# ============ 阶段2: 数据模型 ============
from core.bot.models import (
    CallbackPayload,
    TaskInstruction,
    TaskResult,
    TaskStatus,
    TaskType,
)

# ============ 阶段2: 任务队列 ============
from core.bot.task_queue import (
    TaskQueue,
    get_task_queue,
)

# ============ 阶段2: 回调处理 ============
from core.bot.callback_handler import (
    CallbackHandler,
    get_callback_handler,
)

# ============ 阶段2: SSE客户端 ============
from core.bot.sse_client import (
    SSEClient,
    create_sse_client,
    get_sse_client,
)

# ============ 阶段2: Webhook服务 ============
from core.bot.webhook_server import (
    webhook_router,
    set_task_handler,
)

# ============ 阶段2: 任务执行器 ============
from core.bot.task_executor import (
    TaskExecutor,
    get_task_executor,
)

# ============ 阶段3: 指令解析与分发 ============
from core.bot.task_dispatcher import (
    ImageValidator,
    TaskDispatcher,
)

# ============ 阶段4: 技能系统 ============
from core.bot.skill import (
    Skill,
    SkillContext,
    SkillDefinition,
    SkillRegistry,
    SkillResult,
)

# ============ 阶段4: 技能执行器 ============
from core.bot.skill_executor import (
    SkillExecutor,
    get_skill_executor,
)

# ============ 阶段2+: 对话管理 ============
from core.bot.conversation import (
    ConversationManager,
    ConversationContext,
    get_conversation_manager,
)

# ============ 阶段2+: 重试机制 ============
from core.bot.retry import (
    RetryConfig,
    TimeoutError,
    async_retry,
    async_timeout,
    TaskTimeoutTracker,
    TaskStatusManager,
)

# ============ 阶段2+: 任务状态管理 ============
from core.bot.task_status_manager import (
    TaskStatusManager,
    get_task_status_manager,
)

__all__ = [
    # 阶段1: 配置
    "BotSettings",
    "ConfigManager",
    "ComputeTier",
    "APIProviderType",
    "TierConfig",
    "get_config",
    "get_settings",
    # 阶段1: 速率限制
    "RateLimiter",
    "get_rate_limiter",
    # 阶段1: 算力管理
    "TierManager",
    "get_tier_manager",
    # 阶段2: 数据模型
    "TaskInstruction",
    "TaskStatus",
    "TaskType",
    "TaskResult",
    "CallbackPayload",
    # 阶段2: 任务队列
    "TaskQueue",
    "get_task_queue",
    # 阶段2: 回调处理
    "CallbackHandler",
    "get_callback_handler",
    # 阶段2: SSE客户端
    "SSEClient",
    "create_sse_client",
    "get_sse_client",
    # 阶段2: Webhook服务
    "webhook_router",
    "set_task_handler",
    # 阶段2: 任务执行器
    "TaskExecutor",
    "get_task_executor",
    # 阶段3: 指令解析与分发
    "ImageValidator",
    "TaskDispatcher",
    # 阶段4: 技能系统
    "Skill",
    "SkillContext",
    "SkillDefinition",
    "SkillRegistry",
    "SkillResult",
    # 阶段4: 技能执行器
    "SkillExecutor",
    "get_skill_executor",
    # 阶段2+: 对话管理
    "ConversationManager",
    "ConversationContext",
    "get_conversation_manager",
    # 阶段2+: 重试机制
    "RetryConfig",
    "TimeoutError",
    "async_retry",
    "async_timeout",
    "TaskTimeoutTracker",
    # 阶段2+: 任务状态管理
    "TaskStatusManager",
    "get_task_status_manager",
]
