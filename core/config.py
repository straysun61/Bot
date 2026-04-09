from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Document Processing Bot API"
    SECRET_KEY: str = "your-super-secret-key-for-jwt" # 请在生产环境中更改为环境变量
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120 # 2小时 Token 过期
    API_KEY_NAME: str = "x-api-key"

    # 假设我们有一个预先配置的有效 API KEY (用于演示/测试)
    # 在实际系统中，这通常是在数据库中动态管理的
    VALID_API_KEYS: list[str] = ["demo-api-key-123", "b-end-client-key-456"]

    # === RAG / LLM 配置 (阿里云百炼) ===
    OPENAI_API_KEY: str = "sk-4fdf31ce6b7947eca8d55f40508a97c0"  # 用户的百炼 API Key
    OPENAI_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1" # 百炼 OpenAI 兼容端点
    LLM_MODEL: str = "qwen-plus"  # 日常对话主力模型
    EMBEDDING_MODEL: str = "text-embedding-v3"  # 千问支持的高维嵌入模型

    # 视觉 OCR 配置 - 百度OCR
    BAIDU_API_KEY: str = "6WZeG6p3xQNGxG0Gv1xBfhXC"
    BAIDU_SECRET_KEY: str = "UjUyGs0B3tYVlgGGcTGcRXGlBhW4Q0YE"

    # 向量数据库配置
    CHROMA_DB_PATH: str = "./chroma_db"  # Chroma 数据库本地路径

    # 文档处理配置
    CHUNK_SIZE: int = 500  # 母子文档的子块大小（字符数）
    CHUNK_OVERLAP: int = 50  # 块重叠大小
    PARENT_CHUNK_SIZE: int = 2000  # 母文档块大小

    # 支持的文件类型（包含视觉 OCR 支持）
    SUPPORTED_FILE_TYPES: list[str] = [".pdf", ".txt", ".md", ".doc", ".docx", ".xlsx", ".xls", ".png", ".jpg", ".jpeg"]

settings = Settings()
