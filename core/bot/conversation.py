"""
对话上下文管理器
支持多轮对话上下文继承
"""
import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class Message:
    """对话消息"""
    role: str  # "user" / "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ConversationContext:
    """对话上下文"""
    doc_id: str
    session_id: str
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_active: datetime = field(default_factory=datetime.utcnow)

    def add_message(self, role: str, content: str) -> None:
        """添加消息"""
        self.messages.append(Message(role=role, content=content))
        self.last_active = datetime.utcnow()

    def get_history(self, max_turns: int = 10) -> list[dict]:
        """
        获取对话历史

        Args:
            max_turns: 最大保留轮数

        Returns:
            [{"role": ..., "content": ...}, ...]
        """
        recent = self.messages[-max_turns * 2:] if self.messages else []
        return [{"role": m.role, "content": m.content} for m in recent]

    def get_context_summary(self) -> str:
        """获取上下文摘要"""
        if not self.messages:
            return ""

        lines = [f"=== 对话历史 (共 {len(self.messages)} 条) ==="]
        for i, msg in enumerate(self.messages[-6:], 1):  # 最近3轮
            role_zh = "用户" if msg.role == "user" else "助手"
            lines.append(f"[{role_zh}]: {msg.content[:50]}...")

        return "\n".join(lines)


class ConversationManager:
    """
    对话上下文管理器

    功能：
    1. 为每个文档维护独立的对话会话
    2. 支持多轮对话上下文继承
    3. 自动清理过期会话
    """

    # 对话最大保存时间（秒）
    SESSION_TIMEOUT = 3600  # 1小时
    # 最大保存消息数
    MAX_MESSAGES_PER_SESSION = 100
    # 最多保留历史轮数
    MAX_HISTORY_TURNS = 10

    def __init__(self):
        self._conversations: dict[str, ConversationContext] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """启动管理器"""
        if self._running:
            return
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        print("ConversationManager started")

    async def stop(self) -> None:
        """停止管理器"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        print("ConversationManager stopped")

    async def _cleanup_loop(self) -> None:
        """定期清理过期会话"""
        while self._running:
            try:
                await asyncio.sleep(300)  # 每5分钟检查一次
                self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Cleanup error: {e}")

    def _cleanup_expired(self) -> None:
        """清理过期会话"""
        now = datetime.utcnow()
        expired = []

        for key, ctx in self._conversations.items():
            elapsed = (now - ctx.last_active).total_seconds()
            if elapsed > self.SESSION_TIMEOUT:
                expired.append(key)

        for key in expired:
            del self._conversations[key]

        if expired:
            print(f"Cleaned up {len(expired)} expired conversations")

    def get_or_create_session(self, doc_id: str, session_id: Optional[str] = None) -> ConversationContext:
        """
        获取或创建会话

        Args:
            doc_id: 文档ID
            session_id: 会话ID（可选）

        Returns:
            ConversationContext
        """
        if session_id is None:
            session_id = f"{doc_id}_default"

        key = f"{doc_id}:{session_id}"

        if key not in self._conversations:
            self._conversations[key] = ConversationContext(
                doc_id=doc_id,
                session_id=session_id
            )

        return self._conversations[key]

    def add_user_message(self, doc_id: str, content: str, session_id: Optional[str] = None) -> ConversationContext:
        """添加用户消息"""
        ctx = self.get_or_create_session(doc_id, session_id)
        ctx.add_message("user", content)
        self._trim_messages(ctx)
        return ctx

    def add_assistant_message(self, doc_id: str, content: str, session_id: Optional[str] = None) -> ConversationContext:
        """添加助手消息"""
        ctx = self.get_or_create_session(doc_id, session_id)
        ctx.add_message("assistant", content)
        self._trim_messages(ctx)
        return ctx

    def _trim_messages(self, ctx: ConversationContext) -> None:
        """修剪消息数量"""
        if len(ctx.messages) > self.MAX_MESSAGES_PER_SESSION:
            ctx.messages = ctx.messages[-self.MAX_MESSAGES_PER_SESSION:]

    def get_history(self, doc_id: str, session_id: Optional[str] = None, max_turns: int = 10) -> list[dict]:
        """
        获取对话历史

        Args:
            doc_id: 文档ID
            session_id: 会话ID
            max_turns: 最大轮数

        Returns:
            [{"role": ..., "content": ...}, ...]
        """
        ctx = self.get_or_create_session(doc_id, session_id)
        return ctx.get_history(max_turns)

    def build_prompt_with_context(
        self,
        doc_id: str,
        question: str,
        session_id: Optional[str] = None,
        system_prompt: str = ""
    ) -> tuple[list[dict], str]:
        """
        构建带上下文的 prompt

        Args:
            doc_id: 文档ID
            question: 当前问题
            session_id: 会话ID
            system_prompt: 系统提示词

        Returns:
            (messages_for_llm, context_summary)
        """
        history = self.get_history(doc_id, session_id, self.MAX_HISTORY_TURNS)

        # 构建消息列表
        messages = []

        # 系统提示词
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 对话历史
        messages.extend(history)

        # 当前问题
        messages.append({"role": "user", "content": question})

        # 上下文摘要
        ctx = self.get_or_create_session(doc_id, session_id)
        context_summary = ctx.get_context_summary()

        return messages, context_summary

    def clear_session(self, doc_id: str, session_id: Optional[str] = None) -> bool:
        """
        清除会话

        Args:
            doc_id: 文档ID
            session_id: 会话ID

        Returns:
            是否成功清除
        """
        if session_id is None:
            session_id = f"{doc_id}_default"

        key = f"{doc_id}:{session_id}"

        if key in self._conversations:
            del self._conversations[key]
            return True
        return False

    def get_session_count(self) -> int:
        """获取当前会话数"""
        return len(self._conversations)


# 全局实例
_conversation_manager: Optional[ConversationManager] = None


def get_conversation_manager() -> ConversationManager:
    """获取对话管理器单例"""
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
    return _conversation_manager
