"""
文档处理路由
支持 PDF/图片上传、格式转换、状态查询
"""
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, status
from core.rag_engine import get_rag_engine, DocumentParser
from core.config import settings
from core.bot.models import TaskStatus
from core.bot.task_status_manager import get_task_status_manager
import uuid
import os
import shutil

router = APIRouter()

STORAGE_DIR = "./storage"
MD_STORAGE_DIR = "./storage_md"
ERROR_DIR = "./storage_errors"


def process_document_task(doc_id: str, file_path: str, file_extension: str, user: str):
    """
    后台文档处理任务：
    1. 解析文档为 Markdown 格式
    2. 保存 Markdown 文件（保留格式）
    3. 保存页码映射
    4. 错误状态持久化
    """
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    task_manager = get_task_status_manager()

    logger.info(f"[PROCESS_TASK] Starting task for doc_id={doc_id}, file={file_path}")
    try:
        task_manager.start(doc_id)

        rag_engine = get_rag_engine()
        logger.info(f"[PROCESS_TASK] RAGEngine initialized")

        # 解析文档，返回 Markdown 和页码映射
        result = rag_engine.process_document(
            file_path=file_path,
            file_extension=file_extension,
            metadata={"uploaded_by": user},
            doc_id=doc_id
        )

        markdown_content = result["markdown"]
        page_mappings = result["page_mappings"]

        # 确保存储目录存在
        os.makedirs(MD_STORAGE_DIR, exist_ok=True)

        # 1. 保存 Markdown 文件（完整保留格式）
        md_file_path = os.path.join(MD_STORAGE_DIR, f"{doc_id}.md")
        with open(md_file_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        print(f"Document {doc_id} Markdown saved to {md_file_path}")

        # 2. 保存页码映射
        import json
        mappings_file_path = os.path.join(MD_STORAGE_DIR, f"{doc_id}_mappings.json")
        with open(mappings_file_path, "w", encoding="utf-8") as f:
            json.dump(page_mappings, f, ensure_ascii=False)
        print(f"Page mappings saved to {mappings_file_path}")

        # 3. 同时保存纯文本版本（兼容性）
        text_file_path = os.path.join(STORAGE_DIR, f"{doc_id}_content.txt")
        os.makedirs(STORAGE_DIR, exist_ok=True)
        with open(text_file_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        print(f"Document {doc_id} text saved to {text_file_path}")

        # 检查是否有自校对警告
        warnings = result.get("verification_warnings", [])

        # 保存警告信息到文件（供状态查询使用）
        if warnings:
            warnings_file = os.path.join(MD_STORAGE_DIR, f"{doc_id}.warnings")
            with open(warnings_file, "w", encoding="utf-8") as f:
                json.dump(warnings, f, ensure_ascii=False)

        task_manager.complete(doc_id, {
            "markdown_path": md_file_path,
            "mappings_path": mappings_file_path,
            "page_count": len(page_mappings),
            "content_length": len(markdown_content),
            "warnings": warnings
        })

        logger.info(f"[PROCESS_TASK] Task completed for doc_id={doc_id}")
        return {
            "doc_id": doc_id,
            "markdown_path": md_file_path,
            "mappings_path": mappings_file_path,
            "page_count": len(page_mappings),
            "content_length": len(markdown_content)
        }

    except Exception as e:
        logger.error(f"[PROCESS_TASK] Error processing document {doc_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())

        # 判断错误类型，决定是否可重试
        error_msg = str(e)
        retryable = _is_retryable_error(e)

        task_manager.fail(doc_id, error_msg, retryable=retryable)
        _save_error_file(doc_id, error_msg)

        # 不再 raise，让任务正常结束
        return None


def _is_retryable_error(error: Exception) -> bool:
    """判断错误是否可重试"""
    error_str = str(error).lower()

    # 不可重试的错误类型
    non_retryable_keywords = [
        "unsupported file type",
        "invalid pdf",
        "corrupted",
        "password protected",
        "encrypted",
        "damaged",
        "invalid format",
    ]

    for keyword in non_retryable_keywords:
        if keyword in error_str:
            return False

    # 临时性错误通常可重试
    retryable_keywords = [
        "timeout",
        "connection",
        "network",
        "temporarily unavailable",
        "rate limit",
        "service unavailable",
        "503",
        "502",
        "504",
    ]

    for keyword in retryable_keywords:
        if keyword in error_str:
            return True

    # 默认不可重试（用户需手动重试）
    return False


def _ensure_error_dir() -> None:
    """确保错误目录存在"""
    os.makedirs(ERROR_DIR, exist_ok=True)


def _save_error_file(doc_id: str, error: str) -> None:
    """保存错误信息到文件"""
    _ensure_error_dir()
    error_file = os.path.join(ERROR_DIR, f"{doc_id}.error")
    with open(error_file, "w", encoding="utf-8") as f:
        f.write(error)


def _load_error_file(doc_id: str) -> str:
    """从文件加载错误信息"""
    error_file = os.path.join(ERROR_DIR, f"{doc_id}.error")
    if os.path.exists(error_file):
        try:
            with open(error_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return "未知错误"


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    上传文档，支持 PDF、TXT、MD、图片等格式。

    返回 markdown 文件路径，可直接下载查看完整格式。
    """
    # 1. 检查文件类型
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in settings.SUPPORTED_FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型: {file_extension}。支持的类型: {settings.SUPPORTED_FILE_TYPES}"
        )

    # 2. 生成文档 ID
    doc_id = str(uuid.uuid4())

    # 3. 初始化任务状态
    task_manager = get_task_status_manager()
    task_manager.init_task(doc_id, metadata={"filename": file.filename, "user": "anonymous"})

    # 4. 确保存储目录存在
    os.makedirs(STORAGE_DIR, exist_ok=True)

    # 5. 保存文件
    file_path = os.path.join(STORAGE_DIR, f"{doc_id}_{file.filename}")
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        task_manager.fail(doc_id, f"文件保存失败: {str(e)}", retryable=False)
        _save_error_file(doc_id, f"文件保存失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件保存失败: {str(e)}"
        )

    # 6. 放入后台任务处理
    background_tasks.add_task(
        process_document_task,
        doc_id,
        file_path,
        file_extension,
        "anonymous"
    )

    return {
        "message": f"Successfully uploaded {file.filename}",
        "doc_id": doc_id,
        "status": TaskStatus.PENDING.value
    }


@router.get("/{doc_id}/status")
async def get_document_status(doc_id: str):
    """
    查询文档处理状态

    返回完整的状态信息，包括错误详情（如果失败）
    """
    md_file_path = os.path.join(MD_STORAGE_DIR, f"{doc_id}.md")
    error_file_path = os.path.join(ERROR_DIR, f"{doc_id}.error")

    # 检查是否完成
    if os.path.exists(md_file_path):
        result = {
            "doc_id": doc_id,
            "status": TaskStatus.COMPLETED.value,
            "description": "Document processed and Markdown saved.",
            "md_path": md_file_path
        }
        # 检查是否有警告
        warnings_file = os.path.join(MD_STORAGE_DIR, f"{doc_id}.warnings")
        if os.path.exists(warnings_file):
            try:
                with open(warnings_file, "r", encoding="utf-8") as f:
                    result["warnings"] = json.load(f)
                    result["status"] = "warning"
            except Exception:
                pass
        return result

    # 检查是否有错误文件
    if os.path.exists(error_file_path):
        try:
            with open(error_file_path, "r", encoding="utf-8") as f:
                error_msg = f.read()
        except Exception:
            error_msg = "未知错误"

        # 从文件名判断是 failed 还是 timeout
        # error 文件由 fail() 创建，timeout_error 文件由 timeout() 创建
        timeout_file_path = os.path.join(ERROR_DIR, f"{doc_id}.timeout_error")
        if os.path.exists(timeout_file_path):
            return {
                "doc_id": doc_id,
                "status": TaskStatus.TIMEOUT.value,
                "description": "Document processing timed out.",
                "error": error_msg
            }

        return {
            "doc_id": doc_id,
            "status": TaskStatus.FAILED.value,
            "description": "Document processing failed.",
            "error": error_msg
        }

    # 检查内存中的任务状态
    task_manager = get_task_status_manager()
    task_status = task_manager.get_status(doc_id)

    if task_status:
        status_value = task_status.get("status")
        if isinstance(status_value, TaskStatus):
            status_str = status_value.value
        else:
            status_str = str(status_value)

        return {
            "doc_id": doc_id,
            "status": status_str,
            "description": _get_status_description(status_str)
        }

    # 任务不存在或状态未知
    return {
        "doc_id": doc_id,
        "status": TaskStatus.PENDING.value,
        "description": "Document is waiting to be processed."
    }


def _get_status_description(status: str) -> str:
    """获取状态描述"""
    descriptions = {
        TaskStatus.PENDING.value: "Document is waiting to be processed.",
        TaskStatus.RUNNING.value: "Document is being processed...",
        TaskStatus.COMPLETED.value: "Document processed successfully.",
        TaskStatus.FAILED.value: "Document processing failed.",
        TaskStatus.TIMEOUT.value: "Document processing timed out.",
        TaskStatus.CANCELLED.value: "Document processing was cancelled.",
    }
    return descriptions.get(status, "Unknown status.")


@router.get("/{doc_id}/content")
async def get_document_content(doc_id: str):
    """获取文档的 Markdown 内容"""
    md_file_path = os.path.join(MD_STORAGE_DIR, f"{doc_id}.md")

    if not os.path.exists(md_file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在或尚未处理完成"
        )

    try:
        with open(md_file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {
            "doc_id": doc_id,
            "content": content,
            "format": "markdown"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"读取文档失败: {str(e)}"
        )


@router.get("/{doc_id}/download")
async def download_document(doc_id: str, format: str = "md"):
    """
    下载转换后的文档

    format: md (markdown) 或 txt
    """
    md_file_path = os.path.join(MD_STORAGE_DIR, f"{doc_id}.md")
    text_file_path = os.path.join(STORAGE_DIR, f"{doc_id}_content.txt")

    if format == "md":
        file_path = md_file_path
        media_type = "text/markdown; charset=utf-8"
    else:
        file_path = text_file_path
        media_type = "text/plain; charset=utf-8"

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在或尚未处理完成"
        )

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        from fastapi.responses import StreamingResponse
        import io

        filename = f"{doc_id}.{format}"
        buffer = io.BytesIO(content.encode("utf-8"))
        return StreamingResponse(
            buffer,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}"
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"下载失败: {str(e)}"
        )


@router.get("/{doc_id}/mappings")
async def get_page_mappings(doc_id: str):
    """获取文档的页码映射"""
    mappings_file_path = os.path.join(MD_STORAGE_DIR, f"{doc_id}_mappings.json")

    if not os.path.exists(mappings_file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="页码映射不存在"
        )

    try:
        import json
        with open(mappings_file_path, "r", encoding="utf-8") as f:
            mappings = json.load(f)
        return {
            "doc_id": doc_id,
            "mappings": mappings
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"读取页码映射失败: {str(e)}"
        )


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    """
    删除文档及其所有相关数据（Markdown、向量、错误记录等）
    """
    import logging
    import json
    logger = logging.getLogger(__name__)

    deleted_files = []

    # 1. 删除 Markdown 文件
    md_file = os.path.join(MD_STORAGE_DIR, f"{doc_id}.md")
    if os.path.exists(md_file):
        os.remove(md_file)
        deleted_files.append(md_file)

    # 2. 删除页码映射
    mappings_file = os.path.join(MD_STORAGE_DIR, f"{doc_id}_mappings.json")
    if os.path.exists(mappings_file):
        os.remove(mappings_file)
        deleted_files.append(mappings_file)

    # 3. 删除警告文件
    warnings_file = os.path.join(MD_STORAGE_DIR, f"{doc_id}.warnings")
    if os.path.exists(warnings_file):
        os.remove(warnings_file)
        deleted_files.append(warnings_file)

    # 4. 删除错误记录
    error_file = os.path.join(ERROR_DIR, f"{doc_id}.error")
    if os.path.exists(error_file):
        os.remove(error_file)
        deleted_files.append(error_file)

    timeout_error_file = os.path.join(ERROR_DIR, f"{doc_id}.timeout_error")
    if os.path.exists(timeout_error_file):
        os.remove(timeout_error_file)
        deleted_files.append(timeout_error_file)

    # 5. 从 ChromaDB 中删除该文档的所有向量
    try:
        rag_engine = get_rag_engine()
        collection = rag_engine.vectorstore._collection
        collection.delete(where={"doc_id": doc_id})
        logger.info(f"已从 ChromaDB 删除 doc_id={doc_id} 的向量数据")
    except Exception as e:
        logger.warning(f"从 ChromaDB 删除 doc_id={doc_id} 失败: {e}")

    # 6. 从 doc_bot 向量存储中删除
    try:
        from core.doc_bot import get_doc_bot_v2
        doc_bot = get_doc_bot_v2()
        collection = doc_bot.vectorstore._collection
        collection.delete(where={"doc_id": doc_id})
        logger.info(f"已从 doc_bot ChromaDB 删除 doc_id={doc_id} 的向量数据")
    except Exception as e:
        logger.warning(f"从 doc_bot ChromaDB 删除 doc_id={doc_id} 失败: {e}")

    return {
        "message": f"文档 {doc_id} 已删除",
        "deleted_files": deleted_files
    }
