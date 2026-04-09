"""
技能执行器
将任务分发与技能系统结合
"""
import logging
from typing import Any, Optional

from core.bot.models import TaskInstruction
from core.bot.skill import SkillContext, SkillRegistry, SkillResult
from core.bot.task_dispatcher import TaskDispatcher

logger = logging.getLogger(__name__)


class SkillExecutor:
    """技能执行器"""

    def __init__(self):
        self._initialized = False

    def initialize(self):
        """初始化技能执行器"""
        if self._initialized:
            return

        # 注册内置技能
        from core.bot.skills import register_builtin_skills
        register_builtin_skills()

        # 注册任务类型处理器
        self._register_handlers()

        self._initialized = True
        logger.info("SkillExecutor initialized")

    def _register_handlers(self):
        """注册任务类型处理器"""
        for skill_def in SkillRegistry.list_skills():
            task_type = skill_def.name
            TaskDispatcher.register_handler(
                task_type=task_type,
                handler=self._create_skill_handler(skill_def.name),
                system_prompt=f"You are a {skill_def.description}."
            )

    def _create_skill_handler(self, skill_name: str):
        """创建技能处理器"""
        async def handler(task: TaskInstruction) -> Any:
            # 解析任务指令
            parse_result = TaskDispatcher.parse_instruction(task)

            # 构建技能上下文
            context = SkillContext(
                task_id=task.task_id,
                task_type=task.task_type,
                user_prompt=task.user_prompt,
                images=parse_result.get("images", []),
                system_prompt=parse_result.get("system_prompt", ""),
                metadata=task.metadata
            )

            # 执行技能
            result = await SkillRegistry.execute(skill_name, context)

            if result.success:
                return result.result
            else:
                raise RuntimeError(result.error)

        return handler

    async def execute_task(self, task: TaskInstruction) -> Any:
        """
        执行任务

        Args:
            task: 任务指令

        Returns:
            执行结果
        """
        self.initialize()
        return await TaskDispatcher.dispatch(task)

    def get_available_skills(self) -> list:
        """获取可用技能列表"""
        self.initialize()
        return SkillRegistry.list_skills()


# 全局实例
_skill_executor: Optional[SkillExecutor] = None


def get_skill_executor() -> SkillExecutor:
    """获取技能执行器单例"""
    global _skill_executor
    if _skill_executor is None:
        _skill_executor = SkillExecutor()
    return _skill_executor
