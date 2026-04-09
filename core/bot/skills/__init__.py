"""
技能模块
"""
from core.bot.skills.builtin import (
    FileReadSkill,
    GeneralChatSkill,
    HttpRequestSkill,
    TextProcessSkill,
    register_builtin_skills,
)

__all__ = [
    "GeneralChatSkill",
    "TextProcessSkill",
    "HttpRequestSkill",
    "FileReadSkill",
    "register_builtin_skills",
]
