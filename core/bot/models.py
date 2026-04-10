"""
任务数据模型
定义任务状态、指令结构、结果等
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional, List, Dict

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"       # 待处理
    RUNNING = "running"       # 处理中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"         # 失败
    TIMEOUT = "timeout"       # 超时
    CANCELLED = "cancelled"   # 已取消


class TaskType(str, Enum):
    """任务类型"""
    GENERAL_CHAT = "general_chat"
    DOCUMENT_QA = "document_qa"
    IMAGE_OCR = "image_ocr"
    CUSTOM = "custom"


class TaskInstruction(BaseModel):
    """任务指令结构"""
    task_id: str = Field(..., description="任务唯一ID")
    user_prompt: str = Field(default="", description="用户指令文本")
    image_list: list[str] = Field(default_factory=list, description="图片列表(URL或Base64)")
    image_sequence: Optional[List[str]] = Field(default=None, description="连续图片路径列表（用于多图接力）")
    task_type: str = Field(default="general_chat", description="任务类型")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")
    callback_url: Optional[str] = Field(default=None, description="动态回调地址（由Message Server下发）")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task_123456",
                "user_prompt": "帮我处理这份文档",
                "image_list": ["https://example.com/doc.pdf"],
                "image_sequence": ["img1.png", "img2.png"],
                "task_type": "document_process",
                "metadata": {"source": "scheduler"}
            }
        }


class TaskResult(BaseModel):
    """任务执行结果"""
    task_id: str
    status: TaskStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    warnings: Optional[List[str]] = Field(default=None, description="自校对警告")
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    compute_tier: str = "free"
    metadata: dict[str, Any] = Field(default_factory=dict, description="透传元数据（含callback_url）")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task_123456",
                "status": "completed",
                "result": {"answer": "处理结果"},
                "warnings": ["IMAGE_MISMATCH: ..."],
                "started_at": "2024-01-01T10:00:00",
                "completed_at": "2024-01-01T10:01:00",
                "compute_tier": "high"
            }
        }


class CallbackPayload(BaseModel):
    """回调载荷"""
    task_id: str
    status: TaskStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    warnings: Optional[List[str]] = Field(default=None, description="自校对警告")
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    compute_tier: str = "free"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ==================== 双轨解析架构数据模型 ====================

class AssetType(str, Enum):
    """资产类型"""
    IMAGE = "image"
    TABLE = "table"
    CHART = "chart"


class Asset(BaseModel):
    """文档资产（图片、表格、图表）"""
    asset_id: str
    asset_type: AssetType
    file_path: str          # 本地路径
    mime_type: str          # image/png, image/jpeg
    page_num: Optional[int] = None
    sequence: Optional[int] = None  # 多图连锁中的序号


class ProcessedResult(BaseModel):
    """解析结果"""
    doc_id: str
    markdown: str
    page_mappings: List[dict]
    assets_map: Dict[str, Asset] = Field(default_factory=dict)
    parse_mode: str = "default"       # "vectorized" | "ocr" | "image_sequence"
    table_count: int = 0
    image_count: int = 0
