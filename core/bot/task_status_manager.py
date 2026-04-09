"""
任务状态管理器
"""
import os
from datetime import datetime
from typing import Any, Optional

from core.bot.config import get_config
from core.bot.models import TaskStatus


class TaskStatusManager:
    """
    任务状态管理器

    管理任务状态：pending / running / completed / failed / timeout / cancelled
    支持错误信息持久化到文件系统
    """

    ERROR_DIR = "./storage_errors"

    def __init__(self):
        self._status: dict[str, dict] = {}

    def _ensure_error_dir(self) -> None:
        """确保错误目录存在"""
        os.makedirs(self.ERROR_DIR, exist_ok=True)

    def _get_error_file_path(self, task_id: str) -> str:
        """获取错误文件路径"""
        return os.path.join(self.ERROR_DIR, f"{task_id}.error")

    def _save_error_file(self, task_id: str, error: str) -> None:
        """保存错误信息到文件"""
        self._ensure_error_dir()
        error_file = self._get_error_file_path(task_id)
        with open(error_file, "w", encoding="utf-8") as f:
            f.write(error)

    def _load_error_file(self, task_id: str) -> Optional[str]:
        """从文件加载错误信息"""
        error_file = self._get_error_file_path(task_id)
        if os.path.exists(error_file):
            try:
                with open(error_file, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return None
        return None

    def _remove_error_file(self, task_id: str) -> None:
        """删除错误文件"""
        error_file = self._get_error_file_path(task_id)
        if os.path.exists(error_file):
            try:
                os.remove(error_file)
            except Exception:
                pass

    def init_task(self, task_id: str, metadata: dict = None) -> None:
        """初始化任务"""
        self._status[task_id] = {
            "task_id": task_id,
            "status": TaskStatus.PENDING,
            "created_at": datetime.utcnow(),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
            "retryable": False,
            "metadata": metadata or {}
        }

    def start(self, task_id: str) -> None:
        """标记任务开始"""
        if task_id in self._status:
            self._status[task_id]["status"] = TaskStatus.RUNNING
            self._status[task_id]["started_at"] = datetime.utcnow()

    def complete(self, task_id: str, result: Any = None) -> None:
        """标记任务完成"""
        if task_id in self._status:
            self._status[task_id]["status"] = TaskStatus.COMPLETED
            self._status[task_id]["result"] = result
            self._status[task_id]["completed_at"] = datetime.utcnow()
            self._remove_error_file(task_id)

    def complete_with_warnings(self, task_id: str, result: Any, warnings: list[str]) -> None:
        """标记任务完成但有警告"""
        if task_id in self._status:
            self._status[task_id]["status"] = TaskStatus.COMPLETED
            self._status[task_id]["result"] = result
            self._status[task_id]["warnings"] = warnings
            self._status[task_id]["completed_at"] = datetime.utcnow()

    def fail(self, task_id: str, error: str, retryable: bool = False) -> None:
        """标记任务失败"""
        if task_id in self._status:
            self._status[task_id]["status"] = TaskStatus.FAILED
            self._status[task_id]["error"] = error
            self._status[task_id]["retryable"] = retryable
            self._status[task_id]["completed_at"] = datetime.utcnow()
        self._save_error_file(task_id, error)

    def timeout(self, task_id: str, timeout_seconds: int = None) -> None:
        """标记任务超时"""
        if task_id in self._status:
            self._status[task_id]["status"] = TaskStatus.TIMEOUT
            timeout_msg = f"Task timeout after {timeout_seconds}s" if timeout_seconds else "Task timeout"
            self._status[task_id]["error"] = timeout_msg
            self._status[task_id]["completed_at"] = datetime.utcnow()
        self._save_error_file(task_id, timeout_msg)

    def cancel(self, task_id: str) -> None:
        """标记任务取消"""
        if task_id in self._status:
            self._status[task_id]["status"] = TaskStatus.CANCELLED
            self._status[task_id]["completed_at"] = datetime.utcnow()

    def get_status(self, task_id: str) -> Optional[dict]:
        """获取任务状态"""
        if task_id in self._status:
            status_data = self._status[task_id].copy()
            # 如果有错误但内存中没有，从文件加载
            if status_data.get("error") is None and status_data.get("status") in (TaskStatus.FAILED, TaskStatus.TIMEOUT):
                file_error = self._load_error_file(task_id)
                if file_error:
                    status_data["error"] = file_error
            return status_data
        return None

    def get_error(self, task_id: str) -> Optional[str]:
        """获取任务错误信息（优先从内存，其次从文件）"""
        if task_id in self._status:
            error = self._status[task_id].get("error")
            if error:
                return error
        return self._load_error_file(task_id)

    def is_retryable(self, task_id: str) -> bool:
        """检查任务是否可重试"""
        if task_id in self._status:
            return self._status[task_id].get("retryable", False)
        return False

    def remove(self, task_id: str) -> None:
        """移除任务状态"""
        if task_id in self._status:
            del self._status[task_id]
        self._remove_error_file(task_id)

    def exists(self, task_id: str) -> bool:
        """检查任务是否存在"""
        return task_id in self._status


# 全局实例
_task_status_manager: Optional[TaskStatusManager] = None


def get_task_status_manager() -> TaskStatusManager:
    """获取任务状态管理器"""
    global _task_status_manager
    if _task_status_manager is None:
        _task_status_manager = TaskStatusManager()
    return _task_status_manager
