"""
技能(Skill)接口规范
定义工具的统一接口和元数据
"""
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field


class SkillDefinition(BaseModel):
    """技能定义"""
    name: str = Field(..., description="技能名称")
    description: str = Field(..., description="技能描述")
    parameters: dict[str, Any] = Field(default_factory=dict, description="技能参数Schema")
    examples: list[dict] = Field(default_factory=list, description="使用示例")


class SkillContext(BaseModel):
    """技能执行上下文"""
    task_id: str
    task_type: str
    user_prompt: str
    images: list[dict] = Field(default_factory=list)
    system_prompt: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillResult(BaseModel):
    """技能执行结果"""
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    skill_name: str = ""


class Skill:
    """
    技能基类

    使用方式:
    class MySkill(Skill):
        name = "my_skill"
        description = "My custom skill"

        async def execute(self, context: SkillContext) -> Any:
            # 实现技能逻辑
            return {"message": "done"}
    """

    # 类属性
    name: str = ""
    description: str = ""
    parameters: dict = {}

    @classmethod
    def get_definition(cls) -> SkillDefinition:
        """获取技能定义"""
        return SkillDefinition(
            name=cls.name,
            description=cls.description,
            parameters=cls.parameters
        )

    @classmethod
    async def execute(cls, context: SkillContext) -> Any:
        """
        执行技能

        Args:
            context: 技能执行上下文

        Returns:
            技能执行结果
        """
        raise NotImplementedError("Skill must implement execute method")


class SkillRegistry:
    """技能注册表"""

    _skills: dict[str, type[Skill]] = {}
    _handlers: dict[str, Callable] = {}

    @classmethod
    def register(cls, skill_class: type[Skill] = None, name: str = None):
        """
        注册技能

        Args:
            skill_class: 技能类
            name: 技能名称（可选，默认使用类属性）

        Usage:
            # 方式1: 装饰器
            @SkillRegistry.register
            class MySkill(Skill):
                name = "my_skill"
                ...

            # 方式2: 直接注册
            SkillRegistry.register(MySkill)
        """
        def decorator(skill_cls: type[Skill]):
            skill_name = name or skill_cls.name
            if not skill_name:
                raise ValueError("Skill must have a name")

            cls._skills[skill_name] = skill_cls
            cls._handlers[skill_name] = skill_cls.execute
            return skill_cls

        if skill_class is None:
            return decorator
        else:
            return decorator(skill_class)

    @classmethod
    def get_skill(cls, name: str) -> Optional[type[Skill]]:
        """获取技能类"""
        return cls._skills.get(name)

    @classmethod
    async def execute(cls, name: str, context: SkillContext) -> SkillResult:
        """
        执行技能

        Args:
            name: 技能名称
            context: 执行上下文

        Returns:
            技能执行结果
        """
        if name not in cls._handlers:
            return SkillResult(
                success=False,
                error=f"Skill '{name}' not found",
                skill_name=name
            )

        handler = cls._handlers[name]
        try:
            result = await handler(context)
            return SkillResult(success=True, result=result, skill_name=name)
        except Exception as e:
            return SkillResult(success=False, error=str(e), skill_name=name)

    @classmethod
    def list_skills(cls) -> list[SkillDefinition]:
        """列出所有已注册技能"""
        definitions = []
        for skill_cls in cls._skills.values():
            definitions.append(skill_cls.get_definition())
        return definitions

    @classmethod
    def get_handler(cls, name: str) -> Optional[Callable]:
        """获取技能处理器"""
        return cls._handlers.get(name)

    @classmethod
    def clear(cls):
        """清空注册表"""
        cls._skills.clear()
        cls._handlers.clear()
