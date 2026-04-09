"""
配置管理模块
统一管理所有配置项，从环境变量读取
"""
import os
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class APIProviderType(str, Enum):
    """API提供商类型"""
    OPENAI_COMPATIBLE = "openai-compatible"
    ANTHROPIC_COMPATIBLE = "anthropic-compatible"


class ComputeTier(str, Enum):
    """算力等级"""
    FREE = "free"
    LOW = "low"
    HIGH = "high"
    ULTRA = "ultra"


class TierConfig(BaseModel):
    """单个算力等级配置"""
    key: str = ""
    type: APIProviderType = APIProviderType.OPENAI_COMPATIBLE
    base: str = ""
    model: str = ""


class BotSettings(BaseSettings):
    """机器人配置（从环境变量加载）"""

    # 速率限制
    per_hour_task_limit: int = Field(default=100, alias="PER_HOUR_TASK_LIMIT")

    # 回调配置
    task_callback_url: str = Field(default="", alias="TASK_CALLBACK_URL")
    task_callback_token: str = Field(default="", alias="TASK_CALLBACK_TOKEN")
    task_timeout_seconds: int = Field(default=600, alias="TASK_TIMEOUT_SECONDS")

    # 任务获取模式
    task_receiver_mode: str = Field(default="webhook", alias="TASK_RECEIVER_MODE")
    sse_endpoint: str = Field(default="", alias="SSE_ENDPOINT")

    # 算力配置
    free_tier_key: str = Field(default="", alias="FREE_TIER_KEY")
    free_tier_type: str = Field(default="openai-compatible", alias="FREE_TIER_TYPE")
    free_tier_base: str = Field(default="", alias="FREE_TIER_BASE")
    free_tier_model: str = Field(default="", alias="FREE_TIER_MODEL")

    low_tier_key: str = Field(default="", alias="LOW_TIER_KEY")
    low_tier_type: str = Field(default="openai-compatible", alias="LOW_TIER_TYPE")
    low_tier_base: str = Field(default="", alias="LOW_TIER_BASE")
    low_tier_model: str = Field(default="", alias="LOW_TIER_MODEL")

    high_tier_key: str = Field(default="", alias="HIGH_TIER_KEY")
    high_tier_type: str = Field(default="openai-compatible", alias="HIGH_TIER_TYPE")
    high_tier_base: str = Field(default="", alias="HIGH_TIER_BASE")
    high_tier_model: str = Field(default="", alias="HIGH_TIER_MODEL")

    ultra_tier_key: str = Field(default="", alias="ULTRA_TIER_KEY")
    ultra_tier_type: str = Field(default="anthropic-compatible", alias="ULTRA_TIER_TYPE")
    ultra_tier_base: str = Field(default="", alias="ULTRA_TIER_BASE")
    ultra_tier_model: str = Field(default="", alias="ULTRA_TIER_MODEL")

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "allow"
    }


class ConfigManager:
    """配置管理器（单例）"""

    _instance: Optional["ConfigManager"] = None
    _settings: Optional[BotSettings] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self) -> BotSettings:
        """加载配置"""
        if self._settings is None:
            self._settings = BotSettings()
        return self._settings

    def get_tier_config(self, tier: ComputeTier) -> TierConfig:
        """获取指定算力等级的配置"""
        settings = self.load()

        tier_map = {
            ComputeTier.FREE: TierConfig(
                key=settings.free_tier_key,
                type=APIProviderType(settings.free_tier_type),
                base=settings.free_tier_base,
                model=settings.free_tier_model
            ),
            ComputeTier.LOW: TierConfig(
                key=settings.low_tier_key,
                type=APIProviderType(settings.low_tier_type),
                base=settings.low_tier_base,
                model=settings.low_tier_model
            ),
            ComputeTier.HIGH: TierConfig(
                key=settings.high_tier_key,
                type=APIProviderType(settings.high_tier_type),
                base=settings.high_tier_base,
                model=settings.high_tier_model
            ),
            ComputeTier.ULTRA: TierConfig(
                key=settings.ultra_tier_key,
                type=APIProviderType(settings.ultra_tier_type),
                base=settings.ultra_tier_base,
                model=settings.ultra_tier_model
            ),
        }

        return tier_map.get(tier, TierConfig())

    @property
    def rate_limit(self) -> int:
        """获取全局速率限制"""
        return self.load().per_hour_task_limit

    @property
    def callback_url(self) -> str:
        """获取回调地址"""
        return self.load().task_callback_url

    @property
    def callback_token(self) -> str:
        """获取回调Token"""
        return self.load().task_callback_token

    @property
    def timeout_seconds(self) -> int:
        """获取超时时间（秒）"""
        return self.load().task_timeout_seconds

    @property
    def receiver_mode(self) -> str:
        """获取任务接收模式"""
        return self.load().task_receiver_mode

    @property
    def sse_endpoint(self) -> str:
        """获取SSE端点"""
        return self.load().sse_endpoint


# 全局配置访问
_config_manager: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """获取配置管理器单例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load()
    return _config_manager


def get_settings() -> BotSettings:
    """获取配置（兼容旧接口）"""
    return get_config().load()


# ============ 兼容层：BotConfig & get_bot_config ============

class ComputeTierConfig(BaseModel):
    """算力等级配置（兼容compute_tier模块）"""
    api_key: str = ""
    api_base: str = ""
    model: str = ""


class CallbackConfig(BaseModel):
    """回调配置（兼容旧接口）"""
    access_token: str = ""


class TaskReceiverConfig(BaseModel):
    """任务接收器配置（兼容旧接口）"""
    mode: str = "webhook"
    sse_endpoint: str = ""


class BotConfig(BaseModel):
    """机器人统一配置（兼容旧接口）"""
    callback: CallbackConfig = CallbackConfig()
    task_receiver: TaskReceiverConfig = TaskReceiverConfig()
    compute_tiers: dict[str, ComputeTierConfig] = {}

    @classmethod
    def from_config_manager(cls, cm: ConfigManager) -> "BotConfig":
        """从ConfigManager构建BotConfig"""
        settings = cm.load()
        return cls(
            callback=CallbackConfig(access_token=settings.task_callback_token),
            task_receiver=TaskReceiverConfig(
                mode=settings.task_receiver_mode,
                sse_endpoint=settings.sse_endpoint
            ),
            compute_tiers={
                "free": ComputeTierConfig(
                    api_key=settings.free_tier_key,
                    api_base=settings.free_tier_base,
                    model=settings.free_tier_model
                ),
                "low": ComputeTierConfig(
                    api_key=settings.low_tier_key,
                    api_base=settings.low_tier_base,
                    model=settings.low_tier_model
                ),
                "high": ComputeTierConfig(
                    api_key=settings.high_tier_key,
                    api_base=settings.high_tier_base,
                    model=settings.high_tier_model
                ),
                "ultra": ComputeTierConfig(
                    api_key=settings.ultra_tier_key,
                    api_base=settings.ultra_tier_base,
                    model=settings.ultra_tier_model
                ),
            }
        )


# 全局BotConfig实例
_bot_config: Optional[BotConfig] = None


def get_bot_config() -> BotConfig:
    """获取BotConfig单例（兼容旧接口）"""
    global _bot_config
    if _bot_config is None:
        _bot_config = BotConfig.from_config_manager(get_config())
    return _bot_config
