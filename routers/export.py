"""
MD 导出路由 - 支持将 Markdown 导出为 Word、PDF、HTML、TXT 格式
独立路由，不影响原文档转换和 RAG 功能
"""
import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from core.export_engine import export_md, ExportFormat, get_exporter
from core.bot.task_status_manager import TaskStatusManager, get_task_status_manager

router = APIRouter(prefix="/api/v1/export", tags=["Export"])

MD_STORAGE_DIR = "./storage_md"
EXPORT_STORAGE_DIR = "./storage_export"


class ExportRequest(BaseModel):
    """导出请求"""
    doc_id: str
    format: str  # docx, pdf, html, txt


class ExportResponse(BaseModel):
    """导出响应"""
    success: bool
    doc_id: str
    format: str
    filename: Optional[str] = None
    filepath: Optional[str] = None
    size: Optional[int] = None
    error: Optional[str] = None
    download_url: Optional[str] = None


class BatchExportRequest(BaseModel):
    """批量导出请求"""
    doc_ids: List[str]
    format: str


def _load_md_content(doc_id: str) -> str:
    """加载 Markdown 内容"""
    md_file = os.path.join(MD_STORAGE_DIR, f"{doc_id}.md")
    if os.path.exists(md_file):
        with open(md_file, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def _get_download_url(filename: str, format: str) -> str:
    """获取下载 URL"""
    return f"/api/v1/export/download/{filename}?format={format}"


@router.post("/convert", response_model=ExportResponse)
async def export_document(request: ExportRequest):
    """
    导出文档为指定格式

    支持格式:
    - docx: Word 文档
    - pdf: PDF 文档
    - html: HTML 网页
    - txt: 纯文本
    """
    # 加载 MD 内容
    md_content = _load_md_content(request.doc_id)
    if not md_content:
        raise HTTPException(status_code=404, detail="文档不存在或尚未处理")

    # 验证格式
    supported_formats = [ExportFormat.DOCX, ExportFormat.PDF, ExportFormat.HTML, ExportFormat.TXT]
    if request.format.lower() not in supported_formats:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的格式: {request.format}，支持的格式: {', '.join(supported_formats)}"
        )

    # 执行导出
    result = export_md(request.doc_id, md_content, request.format.lower())

    if result["success"]:
        return ExportResponse(
            success=True,
            doc_id=request.doc_id,
            format=result["format"],
            filename=result["filename"],
            filepath=result["filepath"],
            size=result["size"],
            download_url=_get_download_url(result["filename"], result["format"])
        )
    else:
        return ExportResponse(
            success=False,
            doc_id=request.doc_id,
            format=request.format,
            error=result.get("error", "导出失败")
        )


@router.post("/batch", response_model=dict)
async def batch_export(request: BatchExportRequest):
    """
    批量导出文档

    将多个 MD 文档导出为同一格式
    """
    # 验证格式
    supported_formats = [ExportFormat.DOCX, ExportFormat.PDF, ExportFormat.HTML, ExportFormat.TXT]
    if request.format.lower() not in supported_formats:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的格式: {request.format}"
        )

    results = []
    for doc_id in request.doc_ids:
        md_content = _load_md_content(doc_id)
        if md_content:
            result = export_md(doc_id, md_content, request.format.lower())
            result["doc_id"] = doc_id
            if result["success"]:
                result["download_url"] = _get_download_url(result["filename"], result["format"])
            results.append(result)
        else:
            results.append({
                "success": False,
                "doc_id": doc_id,
                "error": "文档不存在或尚未处理"
            })

    success_count = sum(1 for r in results if r["success"])
    return {
        "total": len(request.doc_ids),
        "success": success_count,
        "failed": len(request.doc_ids) - success_count,
        "results": results
    }


@router.get("/formats")
async def get_supported_formats():
    """获取支持的导出格式列表"""
    return {
        "formats": [
            {
                "id": ExportFormat.DOCX,
                "name": "Word 文档",
                "extension": ".docx",
                "description": "Microsoft Word 兼容格式，适合编辑和排版"
            },
            {
                "id": ExportFormat.PDF,
                "name": "PDF 文档",
                "extension": ".pdf",
                "description": "便携式文档格式，适合阅读和打印"
            },
            {
                "id": ExportFormat.HTML,
                "name": "HTML 网页",
                "extension": ".html",
                "description": "网页格式，适合在线查看"
            },
            {
                "id": ExportFormat.TXT,
                "name": "纯文本",
                "extension": ".txt",
                "description": "无格式纯文本，适合程序处理"
            }
        ]
    }


@router.get("/download/{filename}")
async def download_export(filename: str, format: str = "docx"):
    """
    下载导出的文件
    """
    from fastapi.responses import FileResponse, StreamingResponse
    import io

    # 安全检查：只允许导出目录中的文件
    safe_filename = os.path.basename(filename)
    filepath = os.path.join(EXPORT_STORAGE_DIR, safe_filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")

    # 根据格式设置 MIME 类型
    mime_types = {
        ExportFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ExportFormat.PDF: "application/pdf",
        ExportFormat.HTML: "text/html; charset=utf-8",
        ExportFormat.TXT: "text/plain; charset=utf-8"
    }

    media_type = mime_types.get(format.lower(), "application/octet-stream")

    return FileResponse(
        path=filepath,
        filename=safe_filename,
        media_type=media_type
    )
