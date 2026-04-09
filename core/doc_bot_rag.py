"""
文档处理机器人 - 多轮对话 RAG
集成多轮对话上下文、重试机制、超时处理
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from core.bot.config import get_config
from core.bot.conversation import ConversationManager, get_conversation_manager
from core.bot.retry import (
    RetryConfig,
    TimeoutError,
    async_retry,
    async_timeout,
)
from core.doc_bot import DocBotV2, RealEmbeddingStore, Representation, RepresentationType, get_doc_bot_v2

logger = logging.getLogger(__name__)


class DocBotRAG:
    """
    文档处理机器人 - 支持多轮对话和重试机制

    功能：
    1. 多表示抽取（4种表示），带页码追踪
    2. 真实 Embedding 向量存储
    3. 多轮对话上下文管理
    4. 重试机制和超时处理
    """

    def __init__(self, doc_bot: Optional[DocBotV2] = None):
        self.doc_bot = doc_bot or get_doc_bot_v2()
        self.conversation_manager = get_conversation_manager()
        self.config = get_config()
        self._initialized = False

    async def initialize(self) -> None:
        """初始化"""
        if self._initialized:
            return

        await self.conversation_manager.start()
        self._initialized = True
        logger.info("DocBotRAG initialized")

    async def process_document(
        self,
        doc_id: str,
        md_content: str,
        page_mappings: List[dict] = None
    ) -> dict:
        """
        处理单个文档，带重试机制

        Args:
            doc_id: 文档ID
            md_content: Markdown 格式的文档内容
            page_mappings: 页码映射列表

        Returns:
            处理结果
        """
        try:
            result = await self._process_with_retry(doc_id, md_content, page_mappings)
            return result
        except Exception as e:
            logger.error(f"Failed to process document {doc_id}: {e}")
            raise

    @async_retry(max_attempts=3, base_delay=1.0)
    async def _process_with_retry(
        self,
        doc_id: str,
        md_content: str,
        page_mappings: List[dict]
    ) -> dict:
        """带重试的文档处理"""
        return self.doc_bot.process_single_pdf(doc_id, md_content, page_mappings)

    async def query(
        self,
        question: str,
        doc_id: str,
        session_id: Optional[str] = None,
        rep_types: Optional[List[str]] = None,
        k: int = 5,
        use_context: bool = True,
        system_prompt: str = ""
    ) -> dict:
        """
        多轮对话查询

        Args:
            question: 问题
            doc_id: 文档ID
            session_id: 会话ID
            rep_types: 限定表示类型
            k: 召回数量
            use_context: 是否使用对话上下文
            system_prompt: 系统提示词

        Returns:
            查询结果
        """
        # 初始化
        if not self._initialized:
            await self.initialize()

        # 1. 检索相关文档
        retrieval_results = await self._retrieve_with_retry(
            question=question,
            doc_id=doc_id,
            rep_types=rep_types,
            k=k
        )

        # 2. 构建回复（带上下文）
        if use_context:
            messages, context_summary = self.conversation_manager.build_prompt_with_context(
                doc_id=doc_id,
                question=question,
                session_id=session_id,
                system_prompt=system_prompt or self._get_default_system_prompt()
            )

            # 将检索结果加入上下文
            context_text = self._format_retrieval_context(retrieval_results)
            messages.append({
                "role": "system",
                "content": f"参考文档内容:\n{context_text}"
            })

            # 生成回复
            answer = await self._generate_answer_with_retry(messages)
        else:
            answer = await self._generate_answer_simple(
                question=question,
                context=self._format_retrieval_context(retrieval_results),
                system_prompt=system_prompt
            )

        # 3. 保存对话历史
        self.conversation_manager.add_user_message(doc_id, question, session_id)
        self.conversation_manager.add_assistant_message(doc_id, answer, session_id)

        # 4. 返回结果
        return {
            "question": question,
            "answer": answer,
            "doc_id": doc_id,
            "session_id": session_id or f"{doc_id}_default",
            "retrieval_results": retrieval_results,
            "use_context": use_context
        }

    @async_retry(max_attempts=3, base_delay=1.0)
    async def _retrieve_with_retry(
        self,
        question: str,
        doc_id: str,
        rep_types: Optional[List[str]] = None,
        k: int = 5
    ) -> List[dict]:
        """带重试的检索"""
        result = self.doc_bot.rag_query(
            question=question,
            doc_id=doc_id,
            rep_types=rep_types,
            k=k
        )
        return result.get("results", [])

    async def _generate_answer_simple(
        self,
        question: str,
        context: str,
        system_prompt: str = ""
    ) -> str:
        """简单生成回复（无重试）"""
        import openai
        from core.config import settings

        prompt = f"""{system_prompt or self._get_default_system_prompt()}

参考文档内容:
{context}

用户问题: {question}

请根据文档内容回答用户问题。如果文档中没有相关信息，请明确告知。
"""
        try:
            if not settings.OPENAI_API_KEY:
                return f"[无API Key] 基于文档内容回答: {question}"

            client = openai.OpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_API_BASE or None
            )
            response = client.chat.completions.create(
                model=settings.LLM_MODEL or "gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return f"[LLM错误] {str(e)[:100]}"

    @async_timeout(30.0)
    async def _generate_answer_with_retry(self, messages: List[dict]) -> str:
        """带超时的回复生成"""
        try:
            import openai
            from core.config import settings

            if not settings.OPENAI_API_KEY:
                last_message = messages[-1]["content"] if messages else ""
                return f"[无API Key] {last_message[:100]}..."

            client = openai.OpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_API_BASE or None
            )

            # 转换 messages 格式
            chat_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    chat_messages.append({"role": "system", "content": content})
                elif role == "user":
                    chat_messages.append({"role": "user", "content": content})
                elif role == "assistant":
                    chat_messages.append({"role": "assistant", "content": content})

            response = client.chat.completions.create(
                model=settings.LLM_MODEL or "gpt-3.5-turbo",
                messages=chat_messages,
                temperature=0.3,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            last_message = messages[-1]["content"] if messages else ""
            return f"[LLM错误] {last_message[:100]}..."

    async def query_stream(
        self,
        question: str,
        doc_id: str,
        session_id: Optional[str] = None,
        rep_types: Optional[List[str]] = None,
        k: int = 5,
        use_context: bool = True,
        system_prompt: str = ""
    ):
        """
        流式多轮对话查询

        Yields:
            dict: 包含 delta 内容的事件
        """
        import httpx
        from core.config import settings

        # 初始化
        if not self._initialized:
            await self.initialize()

        # 1. 检索相关文档
        retrieval_results = await self._retrieve_with_retry(
            question=question,
            doc_id=doc_id,
            rep_types=rep_types,
            k=k
        )

        # 2. 构建消息
        if use_context:
            messages, context_summary = self.conversation_manager.build_prompt_with_context(
                doc_id=doc_id,
                question=question,
                session_id=session_id,
                system_prompt=system_prompt or self._get_default_system_prompt()
            )
            # 将检索结果加入上下文
            context_text = self._format_retrieval_context(retrieval_results)
            messages.append({
                "role": "system",
                "content": f"参考文档内容:\n{context_text}"
            })
        else:
            messages = [{
                "role": "system",
                "content": system_prompt or self._get_default_system_prompt()
            }, {
                "role": "user",
                "content": f"参考文档内容:\n{self._format_retrieval_context(retrieval_results)}\n\n用户问题: {question}"
            }]

        # 保存用户消息
        self.conversation_manager.add_user_message(doc_id, question, session_id)

        # 3. 流式生成回复
        if not settings.OPENAI_API_KEY:
            yield {"event": "error", "data": "[无API Key]"}
            return

        try:
            # 使用 httpx 直接实现流式请求
            url = f"{settings.OPENAI_API_BASE}/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": settings.LLM_MODEL or "gpt-3.5-turbo",
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 2000,
                "stream": True
            }

            full_content = ""
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]  # Remove "data: " prefix
                            if data == "[DONE]":
                                break
                            try:
                                import json as json_module
                                chunk_data = json_module.loads(data)
                                delta = chunk_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta:
                                    full_content += delta
                                    yield {"event": "content", "data": delta}
                            except (json_module.JSONDecodeError, KeyError, IndexError):
                                continue

            # 保存助手消息
            self.conversation_manager.add_assistant_message(doc_id, full_content, session_id)

            # 发送完成事件
            yield {
                "event": "done",
                "data": "",
                "retrieval_results": retrieval_results,
                "doc_id": doc_id,
                "session_id": session_id or f"{doc_id}_default"
            }

        except Exception as e:
            logger.error(f"LLM流式调用失败: {e}")
            yield {"event": "error", "data": f"[LLM错误] {str(e)[:100]}"}

    def _get_default_system_prompt(self) -> str:
        """获取默认系统提示词"""
        return """你是一个文档问答助手。请根据提供的文档内容，准确回答用户的问题。
如果文档中没有相关信息，请明确告知用户。回答时请标注信息来源（页码）。"""

    def _format_retrieval_context(self, results: List[dict]) -> str:
        """格式化检索结果为上下文"""
        if not results:
            return "未找到相关内容"

        parts = []
        for i, r in enumerate(results[:3], 1):
            page_num = r.get("page_num", "未知")
            title = r.get("title", "")
            content = r.get("content", "")[:200]
            parts.append(f"【来源{i}】页码: {page_num}\n标题: {title}\n内容: {content}...")

        return "\n\n".join(parts)

    def get_conversation_history(
        self,
        doc_id: str,
        session_id: Optional[str] = None,
        max_turns: int = 10
    ) -> List[dict]:
        """获取对话历史"""
        return self.conversation_manager.get_history(doc_id, session_id, max_turns)

    def clear_conversation(self, doc_id: str, session_id: Optional[str] = None) -> bool:
        """清除对话"""
        return self.conversation_manager.clear_session(doc_id, session_id)


# 全局实例
_doc_bot_rag: Optional[DocBotRAG] = None


def get_doc_bot_rag() -> DocBotRAG:
    """获取 DocBotRAG 单例"""
    global _doc_bot_rag
    if _doc_bot_rag is None:
        _doc_bot_rag = DocBotRAG()
    return _doc_bot_rag
