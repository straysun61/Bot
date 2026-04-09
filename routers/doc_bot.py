"""
文档处理机器人 API - 多轮对话 RAG
"""
import os
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List

from core.doc_bot import get_doc_bot_v2
from core.doc_bot_rag import get_doc_bot_rag
from core.bot.task_status_manager import TaskStatusManager, get_task_status_manager
from core.bot.conversation import get_conversation_manager

router = APIRouter(prefix="/api/v1/doc-bot", tags=["DocBot"])

MD_STORAGE_DIR = "./storage_md"


class ProcessRequest(BaseModel):
    doc_id: str
    md_content: str = ""
    async_process: bool = False


class QueryRequest(BaseModel):
    question: str
    doc_id: Optional[str] = None
    session_id: Optional[str] = None
    rep_types: Optional[List[str]] = None
    k: int = 5
    use_context: bool = True


class QueryResponse(BaseModel):
    question: str
    answer: str
    doc_id: str
    session_id: str
    retrieval_results: List[dict]
    use_context: bool


def _load_page_mappings(doc_id: str) -> List[dict]:
    """加载页码映射"""
    mappings_file = os.path.join(MD_STORAGE_DIR, f"{doc_id}_mappings.json")
    if os.path.exists(mappings_file):
        with open(mappings_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _load_md_content(doc_id: str) -> str:
    """加载 Markdown 内容"""
    md_file = os.path.join(MD_STORAGE_DIR, f"{doc_id}.md")
    if os.path.exists(md_file):
        with open(md_file, "r", encoding="utf-8") as f:
            return f.read()
    return ""


@router.post("/process")
async def process_document(request: ProcessRequest, background_tasks: BackgroundTasks):
    """
    处理文档：多表示抽取 + Embedding

    支持同步和异步处理
    """
    doc_bot = get_doc_bot_v2()
    status_mgr = get_task_status_manager()

    # 初始化任务状态
    status_mgr.init_task(request.doc_id, {"type": "process"})

    # 获取内容
    md_content = request.md_content
    if not md_content:
        md_content = _load_md_content(request.doc_id)

    if not md_content:
        raise HTTPException(status_code=400, detail="No markdown content")

    # 获取页码映射
    page_mappings = _load_page_mappings(request.doc_id)

    if request.async_process:
        # 异步处理
        status_mgr.start(request.doc_id)
        background_tasks.add_task(
            _process_async,
            request.doc_id,
            md_content,
            page_mappings
        )
        return {
            "doc_id": request.doc_id,
            "status": "processing",
            "message": "Document processing started in background"
        }
    else:
        # 同步处理
        status_mgr.start(request.doc_id)
        try:
            result = doc_bot.process_single_pdf(
                doc_id=request.doc_id,
                md_content=md_content,
                page_mappings=page_mappings
            )
            status_mgr.complete(request.doc_id, result)
            return result
        except Exception as e:
            status_mgr.fail(request.doc_id, str(e))
            raise HTTPException(status_code=500, detail=str(e))


async def _process_async(doc_id: str, md_content: str, page_mappings: List[dict]):
    """异步处理文档"""
    doc_bot = get_doc_bot_v2()
    status_mgr = get_task_status_manager()

    try:
        result = doc_bot.process_single_pdf(
            doc_id=doc_id,
            md_content=md_content,
            page_mappings=page_mappings
        )
        status_mgr.complete(doc_id, result)
    except Exception as e:
        logger.error(f"Async process failed for {doc_id}: {e}")
        status_mgr.fail(doc_id, str(e))


@router.post("/query")
async def query_document(request: QueryRequest) -> QueryResponse:
    """
    多轮对话查询

    支持：
    1. 多轮对话上下文
    2. 指定文档范围
    3. 按表示类型过滤
    """
    doc_bot_rag = get_doc_bot_rag()

    # 初始化
    await doc_bot_rag.initialize()

    # 执行查询
    result = await doc_bot_rag.query(
        question=request.question,
        doc_id=request.doc_id,
        session_id=request.session_id,
        rep_types=request.rep_types,
        k=request.k,
        use_context=request.use_context
    )

    return QueryResponse(**result)


@router.post("/query/stream")
async def query_document_stream(request: QueryRequest):
    """
    流式多轮对话查询

    支持：
    1. 多轮对话上下文
    2. SSE 流式输出
    3. 按表示类型过滤
    """
    doc_bot_rag = get_doc_bot_rag()

    async def event_generator():
        async for event in doc_bot_rag.query_stream(
            question=request.question,
            doc_id=request.doc_id,
            session_id=request.session_id,
            rep_types=request.rep_types,
            k=request.k,
            use_context=request.use_context
        ):
            if event["event"] == "content":
                yield f"data: {json.dumps({'type': 'content', 'content': event['data']}, ensure_ascii=False)}\n\n"
            elif event["event"] == "done":
                yield f"data: {json.dumps({'type': 'done', 'retrieval_results': event['retrieval_results'], 'doc_id': event['doc_id'], 'session_id': event['session_id']}, ensure_ascii=False)}\n\n"
            elif event["event"] == "error":
                yield f"data: {json.dumps({'type': 'error', 'error': event['data']}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/conversations/{doc_id}")
async def get_conversation_history(
    doc_id: str,
    session_id: Optional[str] = None,
    max_turns: int = 10
):
    """
    获取对话历史

    Args:
        doc_id: 文档ID
        session_id: 会话ID
        max_turns: 最大轮数
    """
    doc_bot_rag = get_doc_bot_rag()
    history = doc_bot_rag.get_conversation_history(doc_id, session_id, max_turns)

    return {
        "doc_id": doc_id,
        "session_id": session_id or f"{doc_id}_default",
        "history": history,
        "turn_count": len(history) // 2
    }


@router.delete("/conversations/{doc_id}")
async def clear_conversation(doc_id: str, session_id: Optional[str] = None):
    """
    清除对话历史
    """
    doc_bot_rag = get_doc_bot_rag()
    success = doc_bot_rag.clear_conversation(doc_id, session_id)

    return {
        "doc_id": doc_id,
        "session_id": session_id,
        "cleared": success
    }


@router.get("/status/{doc_id}")
async def get_task_status(doc_id: str):
    """
    获取任务状态

    状态包括：pending / running / completed / failed / timeout
    """
    status_mgr = get_task_status_manager()
    status = status_mgr.get_status(doc_id)

    if not status:
        raise HTTPException(status_code=404, detail="Task not found")

    return status


# 保留旧接口兼容
@router.post("/process-v2")
async def process_document_v2(request: ProcessRequest, background_tasks: BackgroundTasks):
    """V2 接口，保留兼容"""
    return await process_document(request, background_tasks)


@router.post("/query-v2")
async def query_document_v2(request: QueryRequest):
    """V2 查询接口，保留兼容"""
    doc_bot = get_doc_bot_v2()

    md_content = _load_md_content(request.doc_id or "")
    if not md_content and not request.doc_id:
        raise HTTPException(status_code=400, detail="doc_id required")

    result = doc_bot.rag_query(
        question=request.question,
        doc_id=request.doc_id,
        rep_types=request.rep_types,
        k=request.k
    )

    return result


@router.get("/representations/{doc_id}")
async def get_representations(doc_id: str):
    """获取文档的所有表示"""
    doc_bot = get_doc_bot_v2()
    result = doc_bot.get_doc_representations(doc_id)

    if not result["representations"]:
        raise HTTPException(status_code=404, detail="Document not found")

    return result


@router.get("/verify-embedding/{doc_id}")
async def verify_embedding(doc_id: str):
    """验证 Embedding"""
    doc_bot = get_doc_bot_v2()
    dim = doc_bot.vector_store.get_embedding_dimension()
    reps = doc_bot.get_doc_representations(doc_id)
    total = sum(len(v) for v in reps["representations"].values())

    return {
        "doc_id": doc_id,
        "embedding_dimension": dim,
        "is_real_embedding": dim > 0,
        "total_representations": total
    }


import logging
logger = logging.getLogger(__name__)
