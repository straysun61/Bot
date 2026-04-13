from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from core.dependencies import get_current_active_user
from core.config import settings
from core.rag_engine import get_rag_engine
from pydantic import BaseModel
from typing import Optional
import json

router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    doc_id: Optional[str] = None  # 可选，如果提供则仅基于该文档进行 QA
    stream: bool = False


class ChatResponse(BaseModel):
    choices: list
    usage: dict


def build_prompt(context_docs: list, query: str) -> str:
    """
    构建 RAG Prompt
    将检索到的上下文与用户问题组装成最终 prompt
    """
    if not context_docs:
        return f"请基于以下背景信息回答问题。如果没有相关信息，请如实说明。\n\n问题: {query}"

    context_text = "\n\n---\n\n".join([
        f"文档 {i+1}:\n{doc.page_content}"
        for i, doc in enumerate(context_docs)
    ])

    prompt = f"""你是一个专业的文档问答助手。请基于以下参考文档内容，准确回答用户的问题。

【参考文档内容】
{context_text}

【用户问题】
{query}

【回答要求】
1. 基于上述参考文档内容进行回答
2. 如果文档中有明确相关信息，请引用原文
3. 如果文档中没有相关信息，请如实说明"文档中没有找到相关内容"
4. 回答要准确、简洁、有条理

【回答】
"""
    return prompt


async def generate_stream_response(prompt: str, api_key: str):
    """
    流式调用 LLM，使用 httpx 直接调用避免 openai SDK proxies 问题
    """
    import httpx

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            f"{settings.OPENAI_API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": settings.LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True
            }
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data)
                        delta = chunk_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            yield f"data: {json.dumps({'content': delta})}\n\n"
                    except json.JSONDecodeError:
                        continue

    yield f"data: {json.dumps({'done': True})}\n\n"


async def generate_non_stream_response(prompt: str, api_key: str) -> dict:
    """
    非流式调用 LLM，使用 httpx 直接调用避免 openai SDK proxies 问题
    """
    import httpx

    response = httpx.post(
        f"{settings.OPENAI_API_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": settings.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 2000
        },
        timeout=60.0
    )
    response.raise_for_status()
    result = response.json()

    return {
        "content": result["choices"][0]["message"]["content"],
        "usage": {
            "prompt_tokens": result.get("usage", {}).get("prompt_tokens", 0),
            "completion_tokens": result.get("usage", {}).get("completion_tokens", 0),
            "total_tokens": result.get("usage", {}).get("total_tokens", 0)
        }
    }


def mock_llm_response(query: str, context_docs: list) -> dict:
    """
    模拟 LLM 响应（当没有 API Key 时使用）
    """
    if context_docs:
        context_preview = "\n".join([
            doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
            for doc in context_docs[:2]
        ])
        response = f"根据检索到的文档内容，我找到了以下相关信息：\n\n{context_preview}\n\n基于以上内容，{query}"
    else:
        response = f"您好！您的问题是：'{query}'。\n\n当前知识库中没有找到完全匹配的内容。请尝试上传相关文档或调整问题表述。"

    return {
        "content": response,
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150
        }
    }


@router.post("/completions")
async def chat_completion(
    request: ChatRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    发起知识库对话。带有依赖注入拦截器。该接口支持 RAG 的问答交互。

    流程：
    1. 将用户 Query 向量化
    2. 从向量数据库检索 top-K 相似的 chunk
    3. 通过 doc_id 映射获取完整母文档上下文
    4. 构造 Prompt 并发送给 LLM
    5. 返回/流式返回 LLM 生成的结果
    """
    if not request.query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="query 不能为空"
        )

    try:
        rag_engine = get_rag_engine()

        # Step 1: 如果指定了 doc_id，先过滤该文档的上下文
        if request.doc_id:
            docs = rag_engine.get_document_by_id(request.doc_id)
            if not docs:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"未找到文档: {request.doc_id}"
                )
            # 使用混合搜索获取完整上下文
            context_docs = rag_engine.hybrid_search(request.query, k=3, mode="hybrid")
            # 过滤只保留指定 doc_id 的文档
            context_docs = [doc for doc in context_docs
                          if doc.metadata.get("doc_id") == request.doc_id]
        else:
            # Step 2: 从整个知识库检索（混合搜索）
            context_docs = rag_engine.hybrid_search(request.query, k=5, mode="hybrid")

        # Step 3: 构建 Prompt
        prompt = build_prompt(context_docs, request.query)

        # Step 4: 调用 LLM 生成响应
        if settings.OPENAI_API_KEY:
            if request.stream:
                # 流式响应
                return StreamingResponse(
                    generate_stream_response(prompt, settings.OPENAI_API_KEY),
                    media_type="text/event-stream"
                )
            else:
                # 非流式响应
                result = await generate_non_stream_response(prompt, settings.OPENAI_API_KEY)
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": result["content"]
                            }
                        }
                    ],
                    "usage": result["usage"]
                }
        else:
            # 无 API Key 时使用模拟响应
            result = mock_llm_response(request.query, context_docs)
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": result["content"]
                        }
                    }
                ],
                "usage": result["usage"]
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG 处理出错: {str(e)}"
        )


@router.get("/health")
async def chat_health():
    """检查 Chat 模块状态"""
    return {
        "status": "ok",
        "rag_engine_initialized": get_rag_engine() is not None,
        "openai_configured": bool(settings.OPENAI_API_KEY)
    }
