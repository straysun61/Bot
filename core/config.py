import os
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    PROJECT_NAME: str = "Document Processing Bot API"
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    API_KEY_NAME: str = "x-api-key"

    VALID_API_KEYS: list[str] = ["demo-api-key-123", "b-end-client-key-456"]

    # === RAG / LLM 配置 (阿里云百炼) ===
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL: str = "qwen-plus"
    EMBEDDING_MODEL: str = "text-embedding-v3"

    # 向量数据库配置
    CHROMA_DB_PATH: str = "./chroma_db"

    # BM25 配置
    BM25_ENABLED: bool = True
    BM25_PERSIST_PATH: str = "./chroma_db/bm25_index.pkl"

    # 文档处理配置
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    PARENT_CHUNK_SIZE: int = 2000

    # 支持的文件类型
    SUPPORTED_FILE_TYPES: list[str] = [".pdf", ".txt", ".md", ".doc", ".docx", ".xlsx", ".xls", ".png", ".jpg", ".jpeg"]

    model_config = {
        "env_file": str(Path(__file__).parent.parent / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "allow",
    }

settings = Settings()
