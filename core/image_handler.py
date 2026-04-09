"""
图片处理模块 - 负责文档中图片的提取、存储和管理
完整链路：提取 -> 保存 -> MD引用 -> 导出还原
"""
import os
import uuid
import logging
from typing import List, Dict, Optional, Tuple
from PIL import Image
import io

logger = logging.getLogger(__name__)

# 图片存储目录
IMAGE_STORAGE_DIR = "./storage_images"


def ensure_image_dir():
    """确保图片目录存在"""
    os.makedirs(IMAGE_STORAGE_DIR, exist_ok=True)


class ImageInfo:
    """图片信息"""
    def __init__(self, image_id: str, original_name: str, stored_path: str, width: int = 0, height: int = 0):
        self.image_id = image_id
        self.original_name = original_name
        self.stored_path = stored_path
        self.width = width
        self.height = height

    def to_dict(self) -> dict:
        return {
            "image_id": self.image_id,
            "original_name": self.original_name,
            "stored_path": self.stored_path,
            "width": self.width,
            "height": self.height
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ImageInfo":
        return cls(
            image_id=data["image_id"],
            original_name=data["original_name"],
            stored_path=data["stored_path"],
            width=data.get("width", 0),
            height=data.get("height", 0)
        )


class ImageHandler:
    """
    图片处理器 - 负责从文档中提取图片、保存、并生成MD引用
    """

    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.images: List[ImageInfo] = []
        ensure_image_dir()

    def save_image(self, image_data: bytes, original_name: str = "", image_format: str = "png") -> ImageInfo:
        """
        保存图片到本地存储

        Args:
            image_data: 图片二进制数据
            original_name: 原始文件名
            image_format: 图片格式 (png, jpg, gif, etc.)

        Returns:
            ImageInfo 对象
        """
        # 生成唯一ID和文件名
        image_id = uuid.uuid4().hex[:12]
        ext = self._get_extension(image_format, original_name)
        filename = f"{self.doc_id}_{image_id}{ext}"
        filepath = os.path.join(IMAGE_STORAGE_DIR, filename)

        # 处理并保存图片
        try:
            img = Image.open(io.BytesIO(image_data))
            width, height = img.size

            # 转换为标准格式保存
            if image_format.lower() in ['jpg', 'jpeg']:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.save(filepath, "JPEG", quality=85, optimize=True)
            elif image_format.lower() == 'png':
                if img.mode == 'RGBA':
                    img.save(filepath, "PNG")
                else:
                    img.save(filepath, "PNG")
            else:
                img.save(filepath, image_format.upper())

            logger.info(f"图片已保存: {filepath}")

        except Exception as e:
            logger.error(f"保存图片失败: {e}, 使用原始数据保存")
            with open(filepath, 'wb') as f:
                f.write(image_data)

        image_info = ImageInfo(
            image_id=image_id,
            original_name=original_name or f"image_{image_id}",
            stored_path=filepath,
            width=width if 'width' in dir() else 0,
            height=height if 'height' in dir() else 0
        )
        self.images.append(image_info)
        return image_info

    def save_image_from_file(self, source_path: str) -> ImageInfo:
        """从已有文件保存图片"""
        with open(source_path, 'rb') as f:
            image_data = f.read()

        # 获取原始文件名
        original_name = os.path.basename(source_path)
        # 推测格式
        ext = os.path.splitext(source_path)[1].lower()

        return self.save_image(image_data, original_name, ext.lstrip('.'))

    def get_markdown_ref(self, image_info: ImageInfo, alt_text: str = "") -> str:
        """
        生成 Markdown 图片引用

        Returns:
            Markdown格式: ![alt](path)
        """
        if not alt_text:
            alt_text = image_info.original_name or image_info.image_id
        # 使用相对路径
        relative_path = image_info.stored_path.replace("\\", "/")
        return f"![{alt_text}]({relative_path})"

    def get_all_markdown_refs(self) -> str:
        """获取所有图片的 Markdown 引用（用于调试）"""
        refs = []
        for img in self.images:
            refs.append(self.get_markdown_ref(img))
        return "\n".join(refs)

    def get_images_metadata(self) -> List[dict]:
        """获取所有图片的元数据"""
        return [img.to_dict() for img in self.images]

    def _get_extension(self, image_format: str, original_name: str) -> str:
        """获取正确的文件扩展名"""
        format_map = {
            'png': '.png',
            'jpg': '.jpg',
            'jpeg': '.jpg',
            'gif': '.gif',
            'bmp': '.bmp',
            'webp': '.webp'
        }

        # 先尝试从格式映射
        ext = format_map.get(image_format.lower())
        if ext:
            return ext

        # 尝试从原始文件名获取
        if original_name:
            name_ext = os.path.splitext(original_name)[1].lower()
            if name_ext in format_map.values():
                return name_ext
            if name_ext:
                return name_ext

        return '.png'  # 默认


def extract_images_from_pdf(file_path: str, doc_id: str) -> Tuple[str, List[ImageInfo]]:
    """
    从 PDF 中提取所有图片

    Args:
        file_path: PDF 文件路径
        doc_id: 文档ID

    Returns:
        Tuple: (markdown_content_with_image_refs, List[ImageInfo])
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF 未安装，无法提取 PDF 图片")
        return "", []

    handler = ImageHandler(doc_id)
    md_parts = []
    image_count = [0]  # 用于生成alt文本

    try:
        pdf_document = fitz.open(file_path)

        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            md_parts.append(f"## 第 {page_num + 1} 页\n")

            # 提取页面中的图片
            image_list = page.get_images(full=True)

            if image_list:
                for img_index, img in enumerate(image_list):
                    try:
                        xref = img[0]
                        base_image = pdf_document.extract_image(xref)

                        if base_image:
                            image_bytes = base_image["image"]
                            ext = base_image["ext"]
                            alt_text = f"PDF第{page_num + 1}页图片{img_index + 1}"

                            image_info = handler.save_image(
                                image_data=image_bytes,
                                original_name=f"p{page_num + 1}_img{img_index + 1}.{ext}",
                                image_format=ext
                            )

                            md_parts.append(handler.get_markdown_ref(image_info, alt_text))
                            image_count[0] += 1

                    except Exception as e:
                        logger.warning(f"提取 PDF 第 {page_num + 1} 页第 {img_index + 1} 张图片失败: {e}")

            # 提取文本
            text = page.get_text()
            if text.strip():
                md_parts.append(f"\n{text.strip()}\n")

        pdf_document.close()

    except Exception as e:
        logger.error(f"PDF 图片提取失败: {e}")

    return "\n".join(md_parts), handler.images


def extract_images_from_docx(file_path: str, doc_id: str) -> Tuple[str, List[ImageInfo]]:
    """
    从 Word DOCX 中提取所有图片

    Args:
        file_path: DOCX 文件路径
        doc_id: 文档ID

    Returns:
        Tuple: (markdown_content_with_image_refs, List[ImageInfo])
    """
    try:
        from docx import Document
        from docx.oxml.ns import qn
    except ImportError:
        logger.warning("python-docx 未安装，无法提取 DOCX 图片")
        return "", []

    handler = ImageHandler(doc_id)
    md_parts = []

    try:
        doc = Document(file_path)

        for para_idx, para in enumerate(doc.paragraphs):
            text = para.text.strip()
            if text:
                md_parts.append(f"{text}\n")

            # 检查段落中的图片 (通过 rId)
            for run in para.runs:
                # 获取 inline shapes
                pass

        # 提取文档级别的图片 (在 rels 中)
        # DOCX 的图片存储在 word/media/ 目录下
        import zipfile
        from lxml import etree

        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                # 列出所有 word/media/ 下的文件
                media_files = [f for f in zip_ref.namelist() if f.startswith('word/media/')]

                for media_file in media_files:
                    try:
                        image_data = zip_ref.read(media_file)
                        original_name = os.path.basename(media_file)
                        ext = os.path.splitext(original_name)[1].lstrip('.')

                        image_info = handler.save_image(
                            image_data=image_data,
                            original_name=original_name,
                            image_format=ext or 'png'
                        )

                        md_parts.append(handler.get_markdown_ref(image_info, f"文档图片{len(handler.images)}"))
                    except Exception as e:
                        logger.warning(f"提取 DOCX 图片失败 {media_file}: {e}")

        except zipfile.BadZipFile:
            logger.warning(f"无法打开 DOCX 文件: {file_path}")

    except Exception as e:
        logger.error(f"DOCX 图片提取失败: {e}")

    return "\n".join(md_parts), handler.images


def embed_images_in_docx(md_content: str, doc_id: str) -> str:
    """
    在导出为 DOCX 时，将 MD 中的图片引用替换为实际图片

    Args:
        md_content: 包含图片引用的 Markdown 内容
        doc_id: 文档ID

    Returns:
        处理后的 Markdown 内容（图片引用保留）
    """
    import re

    # 找到所有图片引用
    pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    matches = re.findall(pattern, md_content)

    # 验证图片文件是否存在
    for alt_text, image_path in matches:
        if os.path.exists(image_path):
            logger.info(f"图片存在: {image_path}")
        else:
            logger.warning(f"图片不存在: {image_path}")

    # 返回原始内容（docx导出时会自动处理本地图片）
    return md_content


def embed_images_in_pdf(md_content: str, doc_id: str) -> str:
    """
    在导出为 PDF 时，保持图片引用（PDF生成时会处理）
    """
    return md_content


def embed_images_in_html(md_content: str, doc_id: str) -> str:
    """
    在导出为 HTML 时，将图片引用转换为完整的 HTML img 标签

    Args:
        md_content: 包含图片引用的 Markdown 内容
        doc_id: 文档ID

    Returns:
        处理后的 Markdown 内容
    """
    import re

    # 找到所有图片引用并转换为完整路径
    pattern = r'!\[([^\]]*)\]\(([^)]+)\)'

    def replace_image_ref(match):
        alt_text = match.group(1)
        relative_path = match.group(2)

        # 转换为绝对路径或保持相对路径
        if not relative_path.startswith(('http://', 'https://', 'data:')):
            # 保持相对路径，浏览器会自动解析
            return f'<img src="{relative_path}" alt="{alt_text}" />'
        return match.group(0)

    return re.sub(pattern, replace_image_ref, md_content)


# 全局图片处理记录 (doc_id -> List[ImageInfo])
_image_records: Dict[str, List[ImageInfo]] = {}


def save_image_records(doc_id: str, images: List[ImageInfo]):
    """保存图片记录"""
    _image_records[doc_id] = images
    logger.info(f"已保存文档 {doc_id} 的 {len(images)} 张图片记录")


def get_image_records(doc_id: str) -> List[ImageInfo]:
    """获取图片记录"""
    return _image_records.get(doc_id, [])


def get_image_record_markdown(doc_id: str) -> str:
    """获取图片记录的 Markdown 引用"""
    images = get_image_records(doc_id)
    if not images:
        return ""

    handler = ImageHandler(doc_id)
    refs = []
    for img in images:
        refs.append(handler.get_markdown_ref(img, img.original_name))

    return "\n\n## 文档图片\n\n" + "\n".join(refs)
