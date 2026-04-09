"""
任务指令解析与分发模块
负责任务指令的校验、解析、类型分发
"""
import base64
import logging
import re
from typing import Any, Callable, Optional

from core.bot.models import TaskInstruction

logger = logging.getLogger(__name__)


class ImageValidator:
    """图片验证器"""

    # 支持的图片格式
    SUPPORTED_FORMATS = {
        "image/jpeg": [".jpg", ".jpeg"],
        "image/png": [".png"],
        "image/gif": [".gif"],
        "image/webp": [".webp"],
        "image/bmp": [".bmp"],
    }

    # Base64图片特征
    BASE64_PATTERN = re.compile(r"^data:image/[\w]+;base64,")

    @classmethod
    def is_base64(cls, value: str) -> bool:
        """检查是否为Base64编码"""
        if cls.BASE64_PATTERN.match(value):
            return True
        # 尝试解码判断
        try:
            if "," in value:
                # data URI格式
                base64.b64decode(value.split(",")[1])
            else:
                base64.b64decode(value)
            return True
        except Exception:
            return False

    @classmethod
    def is_url(cls, value: str) -> bool:
        """检查是否为URL"""
        return value.startswith("http://") or value.startswith("https://")

    @classmethod
    def is_local_path(cls, value: str) -> bool:
        """检查是否为本地路径"""
        return not cls.is_url(value) and not cls.is_base64(value)

    @classmethod
    def validate(cls, image_list: list[str]) -> dict:
        """
        验证图片列表

        Returns:
            {"valid": bool, "images": list, "errors": list}
        """
        errors = []
        validated = []

        for img in image_list:
            if cls.is_base64(img):
                validated.append({"type": "base64", "value": img})
            elif cls.is_url(img):
                validated.append({"type": "url", "value": img})
            elif cls.is_local_path(img):
                validated.append({"type": "local", "value": img})
            else:
                errors.append(f"Invalid image format: {img[:50]}...")

        return {
            "valid": len(errors) == 0,
            "images": validated,
            "errors": errors
        }


class TaskDispatcher:
    """任务分发器"""

    # 内置任务类型处理器
    _handlers: dict[str, Callable] = {}
    # 任务类型对应的System Prompt
    _system_prompts: dict[str, str] = {}

    @classmethod
    def register_handler(cls, task_type: str, handler: Callable, system_prompt: str = None):
        """
        注册任务类型处理器

        Args:
            task_type: 任务类型
            handler: 处理函数 (task: TaskInstruction) -> Any
            system_prompt: 系统提示词
        """
        cls._handlers[task_type] = handler
        if system_prompt:
            cls._system_prompts[task_type] = system_prompt
        logger.info(f"Registered handler for task_type: {task_type}")

    @classmethod
    def get_handler(cls, task_type: str) -> Optional[Callable]:
        """获取任务类型处理器"""
        return cls._handlers.get(task_type)

    @classmethod
    def get_system_prompt(cls, task_type: str) -> str:
        """获取任务类型的System Prompt"""
        return cls._system_prompts.get(task_type, cls._get_default_prompt(task_type))

    @classmethod
    def _get_default_prompt(cls, task_type: str) -> str:
        """获取默认System Prompt"""
        prompts = {
            "general_chat": "You are a helpful AI assistant. Respond to the user's message.",
            "document_process": "You are a document processing assistant. Help users process and analyze documents.",
            "image_ocr": "You are an OCR assistant. Extract text from images accurately.",
            "code_helper": "You are a code assistant. Help users write and debug code.",
        }
        return prompts.get(task_type, "You are a helpful AI assistant.")

    @classmethod
    def parse_instruction(cls, task: TaskInstruction) -> dict:
        """
        解析任务指令

        Args:
            task: 任务指令

        Returns:
            解析结果包含: valid, errors, images, context
        """
        errors = []

        # 1. 校验必填字段
        if not task.task_id:
            errors.append("task_id is required")

        # 2. 校验图片列表
        images_result = {"valid": True, "images": [], "errors": []}
        if task.image_list:
            images_result = ImageValidator.validate(task.image_list)
            if not images_result["valid"]:
                errors.extend(images_result["errors"])

        # 3. 获取System Prompt
        system_prompt = cls.get_system_prompt(task.task_type)

        # 4. 构建执行上下文
        context = {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "user_prompt": task.user_prompt,
            "images": images_result["images"],
            "system_prompt": system_prompt,
            "metadata": task.metadata,
        }

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "images": images_result["images"],
            "context": context
        }

    @classmethod
    async def dispatch(cls, task: TaskInstruction) -> Any:
        """
        分发任务到对应处理器

        Args:
            task: 任务指令

        Returns:
            处理结果

        Raises:
            ValueError: 任务类型不支持或处理失败
        """
        # 1. 解析指令
        parse_result = cls.parse_instruction(task)
        if not parse_result["valid"]:
            raise ValueError(f"Invalid instruction: {parse_result['errors']}")

        # 2. 获取处理器
        handler = cls.get_handler(task.task_type)
        if not handler:
            raise ValueError(f"No handler for task_type: {task.task_type}")

        # 3. 执行处理
        try:
            result = await handler(task)
            return result
        except Exception as e:
            logger.error(f"Handler error for {task.task_type}: {e}")
            raise


# 内置处理器占位
def _default_handler(task: TaskInstruction) -> dict:
    """默认处理器"""
    return {
        "status": "processed",
        "task_id": task.task_id,
        "message": f"Task {task.task_id} processed with type {task.task_type}"
    }
