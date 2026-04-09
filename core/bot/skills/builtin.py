"""
内置技能实现
"""
import asyncio
import json
import logging
from typing import Any

from core.bot.skill import Skill, SkillContext, SkillRegistry

logger = logging.getLogger(__name__)


# ============ 通用对话技能 ============

class GeneralChatSkill(Skill):
    """通用对话技能"""
    name = "general_chat"
    description = "通用对话技能，使用LLM进行自然语言对话"
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "用户消息"}
        },
        "required": ["message"]
    }

    @classmethod
    async def execute(cls, context: SkillContext) -> Any:
        """执行通用对话"""
        from core.bot.tier_manager import get_tier_manager
        from core.bot.config import ComputeTier

        tier_manager = get_tier_manager()
        client = tier_manager.create_client(ComputeTier.HIGH)

        if not client:
            return {"response": f"[模拟回复] {context.user_prompt}"}

        try:
            response = await client.chat.completions.create(
                model=tier_manager.get_model(ComputeTier.HIGH) or "qwen-plus",
                messages=[
                    {"role": "system", "content": context.system_prompt},
                    {"role": "user", "content": context.user_prompt}
                ],
                max_tokens=1000
            )
            return {"response": response.choices[0].message.content}
        except Exception as e:
            logger.error(f"GeneralChatSkill error: {e}")
            return {"response": f"[错误] {str(e)}"}


# ============ 文本处理技能 ============

class TextProcessSkill(Skill):
    """文本处理技能"""
    name = "text_process"
    description = "文本处理技能，支持文本分析、总结、翻译等"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["summarize", "translate", "analyze"],
                "description": "处理动作"
            },
            "text": {"type": "string", "description": "待处理文本"},
            "target_lang": {"type": "string", "description": "目标语言(翻译用)"}
        },
        "required": ["action", "text"]
    }

    @classmethod
    async def execute(cls, context: SkillContext) -> Any:
        """执行文本处理"""
        action = context.metadata.get("action", "analyze")
        text = context.user_prompt

        if not text:
            return {"error": "No text provided"}

        if action == "summarize":
            return await cls._summarize(text)
        elif action == "translate":
            return await cls._translate(text, context.metadata.get("target_lang", "English"))
        else:
            return await cls._analyze(text)

    @classmethod
    async def _summarize(cls, text: str) -> dict:
        """文本摘要"""
        words = text.split()
        summary = " ".join(words[:50])
        if len(words) > 50:
            summary += "..."
        return {"action": "summarize", "summary": summary, "original_length": len(words)}

    @classmethod
    async def _translate(cls, text: str, target_lang: str) -> dict:
        """文本翻译"""
        return {"action": "translate", "original": text, "translated": f"[{target_lang}] {text}"}

    @classmethod
    async def _analyze(cls, text: str) -> dict:
        """文本分析"""
        words = text.split()
        return {
            "action": "analyze",
            "char_count": len(text),
            "word_count": len(words),
            "line_count": len(text.split("\n"))
        }


# ============ HTTP请求技能 ============

class HttpRequestSkill(Skill):
    """HTTP请求技能"""
    name = "http_request"
    description = "发送HTTP请求，获取外部数据"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "请求URL"},
            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
            "headers": {"type": "object"},
            "body": {"type": "object"}
        },
        "required": ["url"]
    }

    @classmethod
    async def execute(cls, context: SkillContext) -> Any:
        """执行HTTP请求"""
        import httpx

        url = context.metadata.get("url")
        method = context.metadata.get("method", "GET")
        headers = context.metadata.get("headers", {})
        body = context.metadata.get("body")

        if not url:
            return {"error": "No URL provided"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=body if body else None
                )
                return {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response.text[:1000]  # 限制返回长度
                }
        except Exception as e:
            return {"error": str(e)}


# ============ 文件处理技能 ============

class FileReadSkill(Skill):
    """文件读取技能"""
    name = "file_read"
    description = "读取本地文件内容"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "encoding": {"type": "string", "description": "文件编码"}
        },
        "required": ["path"]
    }

    @classmethod
    async def execute(cls, context: SkillContext) -> Any:
        """执行文件读取"""
        import os

        path = context.metadata.get("path")
        encoding = context.metadata.get("encoding", "utf-8")

        if not path:
            return {"error": "No path provided"}

        if not os.path.exists(path):
            return {"error": f"File not found: {path}"}

        try:
            with open(path, "r", encoding=encoding) as f:
                content = f.read()
            return {
                "path": path,
                "size": os.path.getsize(path),
                "content": content[:5000]  # 限制返回长度
            }
        except Exception as e:
            return {"error": str(e)}


# ============ 注册内置技能 ============

def register_builtin_skills():
    """注册所有内置技能"""
    SkillRegistry.register(GeneralChatSkill)
    SkillRegistry.register(TextProcessSkill)
    SkillRegistry.register(HttpRequestSkill)
    SkillRegistry.register(FileReadSkill)
    logger.info("Built-in skills registered")


# 自动注册
register_builtin_skills()
