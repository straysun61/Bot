"""
MinerU 高质量 PDF 解析 Skill（预留接口）
支持 CPU 模式和 GPU 模式，需安装 mineru 依赖
"""
from typing import Tuple, Dict


class MinerUSkill:
    """MinerU高质量PDF解析（可选，需安装mineru依赖）"""

    @classmethod
    async def parse(cls, file_path: str) -> Tuple[str, dict]:
        """
        使用MinerU解析PDF，返回(markdown, assets_map)

        用法:
            设置环境变量 USE_MINERU=1 以启用

        安装:
            pip install mineru
        """
        raise NotImplementedError(
            "MinerU未安装。请运行: pip install mineru\n"
            "或在环境变量中设置 USE_MINERU=1 以启用"
        )

    @classmethod
    async def parse_with_tables(cls, file_path: str) -> dict:
        """
        使用 MinerU 解析 PDF，返回结构化表格信息

        Returns:
            {
                "markdown": str,
                "tables": [{"html": str, "json": dict, "position": int}],
                "images": [{"path": str, "page": int}],
                "assets_map": dict
            }
        """
        raise NotImplementedError("MinerU 表格解析功能未实现")
