"""
算力密钥管理模块
支持按等级调用不同API Key，自动兼容OpenAI/Anthropic格式
"""
from typing import Optional

from core.bot.config import APIProviderType, ComputeTier, ConfigManager, get_config


class TierManager:
    """算力等级管理器"""

    def __init__(self, config: Optional[ConfigManager] = None):
        self.config = config or get_config()

    def get_tier_config(self, tier: ComputeTier) -> dict:
        """
        获取指定算力等级的完整配置

        Returns:
            包含 key, type, base, model 的字典
        """
        tier_config = self.config.get_tier_config(tier)
        return {
            "key": tier_config.key,
            "type": tier_config.type,
            "base": tier_config.base,
            "model": tier_config.model
        }

    def get_api_key(self, tier: ComputeTier) -> str:
        """获取指定算力等级的API Key"""
        return self.config.get_tier_config(tier).key

    def get_api_type(self, tier: ComputeTier) -> APIProviderType:
        """获取指定算力等级的API类型"""
        return self.config.get_tier_config(tier).type

    def get_api_base(self, tier: ComputeTier) -> str:
        """获取指定算力等级的API基础地址"""
        return self.config.get_tier_config(tier).base

    def get_model(self, tier: ComputeTier) -> str:
        """获取指定算力等级的模型名称"""
        return self.config.get_tier_config(tier).model

    def create_client(self, tier: ComputeTier) -> Optional[any]:
        """
        为指定算力等级创建API客户端

        Returns:
            对应的客户端实例，如果未配置则返回None
        """
        tier_config = self.config.get_tier_config(tier)

        if not tier_config.key:
            return None

        api_type = tier_config.type
        api_key = tier_config.key
        api_base = tier_config.base

        if api_type == APIProviderType.OPENAI_COMPATIBLE:
            try:
                from openai import AsyncOpenAI
                return AsyncOpenAI(api_key=api_key, base_url=api_base if api_base else None)
            except ImportError:
                return None

        elif api_type == APIProviderType.ANTHROPIC_COMPATIBLE:
            try:
                from anthropic import AsyncAnthropic
                return AsyncAnthropic(api_key=api_key, base_url=api_base if api_base else None)
            except ImportError:
                return None

        return None


# 全局实例
_tier_manager: Optional[TierManager] = None


def get_tier_manager() -> TierManager:
    """获取算力等级管理器（单例）"""
    global _tier_manager
    if _tier_manager is None:
        _tier_manager = TierManager()
    return _tier_manager
