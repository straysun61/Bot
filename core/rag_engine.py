"""
核心 RAG Engine 模块
负责文档解析、向量化和检索
"""
import os
import re
import json
import base64
import uuid
import tempfile
from typing import Optional, Tuple, List, Dict
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain.retrievers.multi_vector import MultiVectorRetriever
from langchain_core.stores import InMemoryStore
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
import httpx

from core.config import settings

# 图片处理模块
from core.image_handler import (
    extract_images_from_pdf,
    extract_images_from_docx,
    save_image_records,
    get_image_record_markdown,
    ImageHandler
)


class FallbackToOCRError(Exception):
    """轨道A解析失败，需要回退到轨道B OCR"""
    pass


class DashScopeEmbeddings(Embeddings):
    """DashScope (阿里云百炼) Embedding 实现"""

    def __init__(self, model: str = "text-embedding-v3", api_key: str = None, base_url: str = None):
        self.model = model
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.base_url = base_url or settings.OPENAI_API_BASE

    def _call_api(self, texts: List[str]) -> List[List[float]]:
        """调用 DashScope embedding API，支持单条失败时逐条处理"""
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

        try:
            response = httpx.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={"model": self.model, "input": texts},
                timeout=60.0
            )
            response.raise_for_status()
            result = response.json()
            return [item["embedding"] for item in result["data"]]
        except httpx.HTTPStatusError as e:
            # 批量失败时，回退到逐条调用
            if e.response.status_code == 400 and len(texts) > 1:
                print(f"[Embedding] 批量请求失败(400)，回退到逐条处理 {len(texts)} 条文本")
                embeddings = []
                for i, text in enumerate(texts):
                    try:
                        single_resp = httpx.post(
                            f"{self.base_url}/embeddings",
                            headers={
                                "Authorization": f"Bearer {self.api_key}",
                                "Content-Type": "application/json"
                            },
                            json={"model": self.model, "input": [text]},
                            timeout=30.0
                        )
                        single_resp.raise_for_status()
                        emb = single_resp.json()["data"][0]["embedding"]
                        embeddings.append(emb)
                        print(f"[Embedding] 第 {i+1}/{len(texts)} 条成功")
                    except Exception as ex:
                        print(f"[Embedding] 第 {i+1}/{len(texts)} 条失败: {ex}，使用模拟向量")
                        embeddings.append(self._mock_embedding(text))
                return embeddings
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入文档，支持分批和重试"""
        # 分批发送，避免单次请求过大
        batch_size = 10
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                batch_embeddings = self._call_api(batch)
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                print(f"[EMBED] Batch {i//batch_size} failed: {e}")
                # 尝试逐条发送，定位问题
                for j, text in enumerate(batch):
                    try:
                        emb = self._call_api([text])
                        all_embeddings.extend(emb)
                    except Exception as e2:
                        print(f"[EMBED] Text {i+j} failed: {e2}")
                        print(f"[EMBED]   Text: {repr(text[:200])}")
                        # 使用零向量作为fallback
                        all_embeddings.append([0.0] * 1024)
        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        """嵌入单个查询"""
        return self._call_api([text])[0]

    def _mock_embedding(self, text: str) -> List[float]:
        """生成模拟向量（当 API 调用失败时使用）"""
        import hashlib
        hash_bytes = hashlib.md5(text.encode()).digest()
        return [float(b) / 255.0 for b in hash_bytes[:16]] * 8


class VisionOCR:
    """视觉大模型 OCR 处理器 - 使用阿里云百炼 qwen-vl-plus"""

    SYSTEM_PROMPT = """你是一个顶级的 OCR 与排版复原专家。请识别并提取出图片里的所有文本，特别是手写文字，如实复现，不要编造。保持原有的排版格式，如果有多栏布局请保持栏序。"""

    RELAY_SYSTEM_PROMPT = """{base_prompt}

【接力上下文】以下是前一页/图片的内容摘要：
{previous_summary}

请判断当前图片是否为前一页的逻辑延续（如同一个公式的推演、同一段笔记的继续）。
如果是，请保持上下文连贯，继续输出。
如果不是，请独立处理当前内容。

请在输出开头标注 [CONTINUATION] 或 [NEW_START] 以示区分。"""

    MAX_IMAGE_SIZE = 10 * 1024 * 1024

    @classmethod
    def extract_text_from_image(cls, image_path: str) -> str:
        return cls._call_vision(image_path, cls.SYSTEM_PROMPT)

    @classmethod
    async def extract_with_context(
        cls, image_path: str, context: str = "", is_continuation: bool = False
    ) -> str:
        """带接力上下文的 OCR"""
        if is_continuation and context:
            prompt = cls.RELAY_SYSTEM_PROMPT.format(
                base_prompt=cls.SYSTEM_PROMPT,
                previous_summary=context
            )
        else:
            prompt = cls.SYSTEM_PROMPT
        return cls._call_vision(image_path, prompt)

    @classmethod
    def _call_vision(cls, image_path: str, system_prompt: str) -> str:
        """调用视觉大模型进行 OCR（使用 httpx 直接调用，避免 openai SDK 的 proxies 问题）"""
        if not settings.OPENAI_API_KEY:
            return f"[模拟 OCR 结果] 已从图片 {os.path.basename(image_path)} 中提取文本。"

        actual_path = image_path
        file_size = os.path.getsize(image_path)

        if file_size > cls.MAX_IMAGE_SIZE:
            print(f"图片太大 ({file_size / 1024 / 1024:.1f}MB)，正在压缩...")
            actual_path = cls._compress_image(image_path)
            compressed_size = os.path.getsize(actual_path)
            print(f"压缩完成: {compressed_size / 1024 / 1024:.1f}MB")

        with open(actual_path, "rb") as image_file:
            image_base64 = base64.b64encode(image_file.read()).decode("utf-8")

        # 使用 httpx 直接调用，避免 openai SDK 和 httpx 版本不兼容导致的 proxies 问题
        try:
            response = httpx.post(
                f"{settings.OPENAI_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "qwen-vl-plus",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                            ]
                        }
                    ],
                    "max_tokens": 4096
                },
                timeout=120.0
            )
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            print(f"Vision OCR HTTP 错误: {e.response.status_code} - {e.response.text[:200]}")
            raise Exception(f"Vision OCR 调用失败: {e.response.status_code}")
        except Exception as e:
            print(f"Vision OCR 调用异常: {str(e)}")
            raise

        if actual_path != image_path and os.path.exists(actual_path):
            try:
                os.remove(actual_path)
            except:
                pass

        return content

    @staticmethod
    def slice_long_image(image_path: str, overlap_px: int = 200, max_height: int = 4096) -> List[str]:
        """
        带重叠的长图切分
        检测图片高度 > max_height 时，按 max_height 步长切分
        相邻切片之间保留 overlap_px 重叠区域

        Returns:
            切片路径列表。如果不需要切分，返回 [image_path]
        """
        from PIL import Image

        img = Image.open(image_path)
        width, height = img.size

        if height <= max_height:
            return [image_path]

        slices = []
        base_name = os.path.splitext(image_path)[0]
        slice_idx = 0
        y_start = 0

        while y_start < height:
            y_end = min(y_start + max_height, height)

            if slice_idx > 0:
                y_start = max(0, y_end - max_height + overlap_px)
                y_end = min(y_start + max_height, height)

            slice_img = img.crop((0, y_start, width, y_end))
            slice_path = f"{base_name}_slice_{slice_idx:03d}.png"
            slice_img.save(slice_path)
            slices.append(slice_path)

            y_start = y_end
            slice_idx += 1

        return slices

    @classmethod
    def _compress_image(cls, image_path: str) -> str:
        """压缩图片使其小于 MAX_IMAGE_SIZE"""
        from PIL import Image
        import tempfile

        img = Image.open(image_path)
        quality = 85
        temp_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        temp_path = temp_file.name
        temp_file.close()

        while True:
            img.save(temp_path, "JPEG", quality=quality, optimize=True)
            if os.path.getsize(temp_path) < cls.MAX_IMAGE_SIZE or quality <= 20:
                break
            quality -= 10

        return temp_path

    @classmethod
    def extract_text_from_pdf_page_image(cls, page_image_path: str) -> str:
        """从 PDF 页面图片中提取文本"""
        return cls.extract_text_from_image(page_image_path)


class DocumentParser:
    """
    文档解析器，支持 PDF、TXT、MD、图片等格式

    双轨解析架构：
    - 轨道A: PyMuPDF4LLM（矢量PDF，保留表格/图片结构）
    - 轨道B: Vision OCR（扫描件/照片，接力式多图处理）
    """

    MIN_TEXT_THRESHOLD = 50

    # ==================== Track A: 矢量PDF解析 ====================

    @classmethod
    def parse_pdf_vectorized(cls, file_path: str, doc_id: str = None) -> Tuple[str, List[dict], dict]:
        """
        轨道A: 使用 PyMuPDF4LLM 解析矢量PDF
        保留表格结构和图片引用

        Returns:
            (markdown_text, page_mappings, assets_map)
        """
        if doc_id is None:
            doc_id = uuid.uuid4().hex[:12]

        try:
            import pymupdf4llm
        except ImportError:
            print("pymupdf4llm 未安装，回退到 pdfplumber...")
            md_text, page_mappings = cls._parse_pdf_pdfplumber(file_path, doc_id)
            return md_text, page_mappings, {}

        # 使用 pymupdf4llm 转换为 Markdown（保留表格语法）
        markdown_text = pymupdf4llm.to_markdown(file_path)

        # 提取图片
        all_images = []
        try:
            md_with_images, extracted_images = extract_images_from_pdf(file_path, doc_id)
            if extracted_images:
                save_image_records(doc_id, extracted_images)
                image_refs = get_image_record_markdown(doc_id)
                if image_refs:
                    markdown_text = markdown_text + "\n\n" + image_refs
                all_images = extracted_images
                print(f"从 PDF 提取了 {len(extracted_images)} 张图片")
        except Exception as img_err:
            print(f"PDF 图片提取失败: {img_err}")

        # 构建 page_mappings
        page_mappings = []
        current_pos = 0
        pages = markdown_text.split("\n\n")
        for i, page_content in enumerate(pages):
            page_mappings.append({
                "page_num": i + 1,
                "content": page_content,
                "start_char": current_pos,
                "end_char": current_pos + len(page_content)
            })
            current_pos += len(page_content) + 2

        # 构建 assets_map
        assets_map = {}
        for img_info in all_images:
            assets_map[img_info.image_id] = {
                "asset_id": img_info.image_id,
                "asset_type": "image",
                "file_path": img_info.stored_path,
                "mime_type": "image/png",
                "page_num": None,
                "sequence": len(assets_map)
            }

        # 检测是否需要 fallback
        if len(markdown_text.strip()) == 0:
            raise FallbackToOCRError("PyMuPDF4LLM 返回空结果，触发 OCR 回退")

        return markdown_text, page_mappings, assets_map

    @classmethod
    def _parse_pdf_pdfplumber(cls, file_path: str, doc_id: str = None) -> Tuple[str, List[dict]]:
        """使用 pdfplumber 解析 PDF（兼容旧方法）"""
        try:
            import pdfplumber
        except ImportError:
            raise ImportError("pdfplumber 未安装，请运行: pip install pdfplumber")

        if doc_id is None:
            doc_id = uuid.uuid4().hex[:12]

        page_mappings = []
        all_text = []
        current_char_pos = 0

        try:
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    page_text = page.extract_text() or ""

                    if len(page_text.strip()) < cls.MIN_TEXT_THRESHOLD:
                        print(f"第 {page_num} 页文本量异常少，启用 Vision OCR...")
                        page_text = cls._parse_pdf_page_with_vision(file_path, page_num)
                    else:
                        page_text = cls._convert_to_markdown(page_text, page_num)

                    start_char = current_char_pos
                    end_char = current_char_pos + len(page_text)

                    page_mappings.append({
                        "page_num": page_num,
                        "content": page_text,
                        "start_char": start_char,
                        "end_char": end_char
                    })

                    all_text.append(page_text)
                    current_char_pos = end_char

            try:
                import fitz
                md_with_images, extracted_images = extract_images_from_pdf(file_path, doc_id)
                if extracted_images:
                    save_image_records(doc_id, extracted_images)
                    image_refs = get_image_record_markdown(doc_id)
                    all_text.append(image_refs)
                    print(f"从 PDF 提取了 {len(extracted_images)} 张图片")
            except Exception as img_err:
                print(f"PDF 图片提取失败: {img_err}")

        except Exception as e:
            print(f"PDF 解析失败: {e}")
            all_text, page_mappings = cls._parse_pdf_with_vision_fallback(file_path)

        return "\n\n".join(all_text), page_mappings

    @classmethod
    def parse_pdf(cls, file_path: str, doc_id: str = None) -> Tuple[str, List[dict]]:
        """
        从 PDF 文件中提取文本，返回 (markdown_content, page_mappings)
        优先尝试轨道A（PyMuPDF4LLM），失败后回退到 pdfplumber
        """
        try:
            md_text, page_mappings, assets_map = cls.parse_pdf_vectorized(file_path, doc_id)
            return md_text, page_mappings
        except FallbackToOCRError:
            print("轨道A结果为空，回退到 pdfplumber 解析...")
            return cls._parse_pdf_pdfplumber(file_path, doc_id)
        except Exception as e:
            print(f"轨道A解析失败: {e}，回退到 pdfplumber...")
            return cls._parse_pdf_pdfplumber(file_path, doc_id)

    @classmethod
    async def parse_image_sequence_relay(
        cls, image_paths: List[str], doc_id: str = None
    ) -> Tuple[str, List[dict], dict]:
        """
        轨道B: 多图接力处理
        每张图继承前一张的摘要，保持上下文连贯
        """
        if doc_id is None:
            doc_id = uuid.uuid4().hex[:12]

        accumulated_text = []
        page_mappings = []
        assets_map = {}
        prev_summary = ""
        current_pos = 0

        for i, img_path in enumerate(image_paths):
            slices = VisionOCR.slice_long_image(img_path)
            needs_slicing = len(slices) > 1

            for j, slice_path in enumerate(slices):
                is_continuation = (i > 0 or j > 0)

                ocr_result = await VisionOCR.extract_with_context(
                    slice_path,
                    context=prev_summary,
                    is_continuation=is_continuation
                )

                if needs_slicing and slice_path != img_path:
                    try:
                        os.remove(slice_path)
                    except:
                        pass

                page_num = i + 1
                md_text = cls._convert_to_markdown(ocr_result, page_num)
                accumulated_text.append(md_text)

                page_mappings.append({
                    "page_num": page_num,
                    "content": md_text,
                    "start_char": current_pos,
                    "end_char": current_pos + len(md_text)
                })
                current_pos += len(md_text) + 2

                prev_summary = cls._generate_page_summary(ocr_result)

        full_markdown = "\n\n".join(accumulated_text)
        return full_markdown, page_mappings, assets_map

    @classmethod
    def _generate_page_summary(cls, text: str) -> str:
        """提取当前页的关键信息作为接力摘要"""
        lines = text.strip().split("\n")
        titles = [l.strip("# ") for l in lines if l.startswith("#")]
        formula_refs = re.findall(r'\(公式\s*[\d.]+\)', text)

        summary_parts = []
        if titles:
            summary_parts.append(f"标题: {'; '.join(titles[:3])}")
        if formula_refs:
            summary_parts.append(f"公式: {', '.join(formula_refs[:3])}")
        if text.strip():
            summary_parts.append(f"内容: {text.strip()[:200]}...")

        return "\n".join(summary_parts) if summary_parts else text.strip()[:300]

    # ==================== 辅助方法 ====================

    @classmethod
    def _convert_to_markdown(cls, text: str, page_num: int) -> str:
        """将提取的文本转换为 Markdown 格式，保留结构"""
        lines = text.split('\n')
        markdown_lines = [f"# 第 {page_num} 页\n"]

        for line in lines:
            line = line.strip()
            if not line:
                markdown_lines.append("")
                continue

            if re.match(r'^(第[一二三四五六七八九十\d]+[章节条项]|[①②③④⑤⑥⑦⑧⑨⑩])\s*', line):
                heading_match = re.search(r'([^\s].+)$', line)
                if heading_match:
                    markdown_lines.append(f"## {heading_match.group(1)}")
                else:
                    markdown_lines.append(f"## {line}")
            elif re.match(r'^[\d]+[.、]\s+', line) or re.match(r'^[a-zA-Z][.、]\s+', line):
                content = re.sub(r'^[\d]+[.、]\s+', '', line)
                content = re.sub(r'^[a-zA-Z][.、]\s+', '', content)
                markdown_lines.append(f"1. {content}")
            elif '|' in line and line.count('|') >= 2:
                markdown_lines.append(line)
            else:
                markdown_lines.append(line)

        return "\n".join(markdown_lines)

    @classmethod
    def _parse_pdf_page_with_vision(cls, file_path: str, page_num: int) -> str:
        """使用 Vision OCR 处理单个 PDF 页面"""
        try:
            import fitz
        except ImportError:
            raise ImportError("PyMuPDF 未安装，请运行: pip install PyMuPDF")

        try:
            pdf_document = fitz.open(file_path)
            if page_num > len(pdf_document):
                return ""

            page = pdf_document[page_num - 1]
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)

            temp_image = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            temp_path = temp_image.name
            temp_image.close()
            pix.save(temp_path)
            pdf_document.close()

            try:
                page_text = VisionOCR.extract_text_from_pdf_page_image(temp_path)
                return cls._convert_to_markdown(page_text, page_num)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        except Exception as e:
            print(f"第 {page_num} 页 Vision OCR 失败: {e}")
            return f"[第 {page_num} 页 OCR 提取失败]"

    @classmethod
    def _parse_pdf_with_vision_fallback(cls, file_path: str) -> Tuple[str, List[dict]]:
        """使用 Vision OCR 处理整个 PDF（回退方案）"""
        try:
            import fitz
        except ImportError:
            raise ImportError("PyMuPDF 未安装，请运行: pip install PyMuPDF")

        page_mappings = []
        all_text = []
        temp_image_paths = []

        try:
            pdf_document = fitz.open(file_path)

            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat)

                temp_image = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                temp_path = temp_image.name
                temp_image.close()
                pix.save(temp_path)
                temp_image_paths.append(temp_path)

                page_text = VisionOCR.extract_text_from_pdf_page_image(temp_path)
                md_text = cls._convert_to_markdown(page_text, page_num + 1)

                page_mappings.append({
                    "page_num": page_num + 1,
                    "content": md_text,
                    "start_char": sum(len(t) + 2 for t in all_text),
                    "end_char": sum(len(t) + 2 for t in all_text) + len(md_text)
                })

                all_text.append(md_text)

            pdf_document.close()

        finally:
            for temp_path in temp_image_paths:
                try:
                    os.remove(temp_path)
                except:
                    pass

        return "\n\n".join(all_text), page_mappings

    @classmethod
    def parse_image(cls, file_path: str) -> Tuple[str, List[dict]]:
        """直接解析图片文件，使用 Vision LLM OCR"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"图片文件不存在: {file_path}")

        page_num = 1
        text = VisionOCR.extract_text_from_image(file_path)
        md_text = cls._convert_to_markdown(text, page_num)

        mappings = [{
            "page_num": page_num,
            "content": md_text,
            "start_char": 0,
            "end_char": len(md_text)
        }]

        return md_text, mappings

    @classmethod
    def parse_txt(cls, file_path: str) -> Tuple[str, List[dict]]:
        """从 TXT 文件读取文本"""
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

        lines = text.split('\n')
        md_lines = []
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                md_lines.append("")
                continue

            if len(line) < 50 and not line[-1] in '。！？；：' and i < len(lines) - 1:
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if len(next_line) > 20:
                    md_lines.append(f"## {line}")
                    continue

            md_lines.append(line)

        md_text = "\n".join(md_lines)

        mappings = [{
            "page_num": 1,
            "content": md_text,
            "start_char": 0,
            "end_char": len(md_text)
        }]

        return md_text, mappings

    @classmethod
    def parse_docx(cls, file_path: str, doc_id: str = None) -> Tuple[str, List[dict]]:
        """从 Word .docx 文件提取文本和图片（图片插入到正确位置）"""
        from docx import Document
        import zipfile

        if doc_id is None:
            doc_id = uuid.uuid4().hex[:12]

        doc = Document(file_path)
        handler = ImageHandler(doc_id)

        # Step 1: 从 ZIP 提取所有图片并保存，建立 rId -> ImageInfo 映射
        rId_to_image = {}
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                media_files = [f for f in zip_ref.namelist() if f.startswith('word/media/')]
                for mf in media_files:
                    fname = os.path.basename(mf)
                    if fname:
                        try:
                            image_data = zip_ref.read(mf)
                            ext = os.path.splitext(fname)[1].lstrip('.')
                            img_info = handler.save_image(
                                image_data=image_data,
                                original_name=fname,
                                image_format=ext or 'png'
                            )
                            # 用文件名和完整路径都建立映射
                            rId_to_image[fname] = img_info
                        except Exception as e:
                            print(f"提取图片失败 {mf}: {e}")
        except Exception as e:
            print(f"无法打开 DOCX ZIP: {e}")

        # Step 2: 建立 rId -> 图片文件名 映射（从文档关系）
        rId_to_filename = {}
        for r_id, rel in doc.part.rels.items():
            if 'image' in str(rel.reltype).lower():
                target = rel.target_ref
                rId_to_filename[r_id] = os.path.basename(target)

        # Step 3: 为每个段落收集其图片引用
        para_image_refs = {}  # para_index -> [img_md, ...]
        for shape in doc.inline_shapes:
            try:
                blip = shape._inline.graphic.graphicData.pic.blipFill.blip
                r_id = blip.embed
                fname = rId_to_filename.get(r_id)
                if fname and fname in rId_to_image:
                    img = rId_to_image[fname]
                    img_md = f"![{img.original_name}]({img.stored_path.replace(chr(92), '/')})"
                    # 从 shape._inline 向上找到 w:p 段落元素
                    drawing_el = shape._inline.getparent()
                    current = drawing_el
                    para_el = None
                    while current is not None:
                        if current.tag.endswith('}p'):
                            para_el = current
                            break
                        current = current.getparent()
                    # 找到对应的段落索引
                    if para_el is not None:
                        for p_idx, para in enumerate(doc.paragraphs):
                            if para._element is para_el:
                                para_image_refs.setdefault(p_idx, []).append(img_md)
                                break
            except Exception:
                pass

        # Step 4: 遍历段落，插入文本和图片
        paragraphs = []
        mappings = []
        current_pos = 0

        for para_idx, para in enumerate(doc.paragraphs):
            # 先插入该段落的图片
            for img_md in para_image_refs.get(para_idx, []):
                paragraphs.append(img_md)

            text = para.text.strip()
            if text:
                # 检测标题样式
                is_heading = False
                heading_level = 2
                if para.style.name.startswith('Heading'):
                    is_heading = True
                    level = int(para.style.name[-1]) if para.style.name[-1].isdigit() else 2
                    heading_level = min(level, 6)
                elif re.match(r'^[一二三四五六七八九十]+[、.]', text):
                    is_heading = True
                    heading_level = 1
                elif re.match(r'^\d+[、.]\s', text):
                    is_heading = True
                    heading_level = 2
                elif re.match(r'^\d+\.\d+[、.]\s', text):
                    is_heading = True
                    heading_level = 3
                elif re.match(r'^第[一二三四五六七八九十\d]+[章节条]', text):
                    is_heading = True
                    heading_level = 1

                if is_heading:
                    prefix = "#" * heading_level
                    text = f"{prefix} {text}"

                start_char = current_pos
                end_char = current_pos + len(text)

                paragraphs.append(text)
                mappings.append({
                    "page_num": len(mappings) + 1,
                    "content": text,
                    "start_char": start_char,
                    "end_char": end_char
                })
                current_pos = end_char + 2

        # 提取表格
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join([cell.text.strip() for cell in row.cells])
                if row_text:
                    paragraphs.append(f"| {row_text} |")
                    mappings.append({
                        "page_num": len(mappings) + 1,
                        "content": f"| {row_text} |",
                        "start_char": current_pos,
                        "end_char": current_pos + len(row_text) + 4
                    })
                    current_pos += len(row_text) + 4

        md_text = "\n\n".join(paragraphs)

        # 记录图片
        if handler.images:
            save_image_records(doc_id, handler.images)
            print(f"从 DOCX 提取了 {len(handler.images)} 张图片")

        return md_text, mappings

    @classmethod
    def parse_doc(cls, file_path: str) -> Tuple[str, List[dict]]:
        """从 Word .doc 文件提取文本（支持 Windows 和 Linux）"""
        import platform
        system = platform.system()

        # Windows: 使用 win32com
        if system == "Windows":
            try:
                import win32com.client
                import pythoncom
                pythoncom.CoInitialize()
                try:
                    word = win32com.client.Dispatch("Word.Application")
                    word.Visible = False
                    doc = word.Documents.Open(os.path.abspath(file_path))
                    text = doc.Content.Text
                    doc.Close(False)
                    word.Quit()
                    return cls._text_to_markdown(text)
                finally:
                    pythoncom.CoUninitialize()
            except ImportError:
                raise ImportError("pywin32 未安装，请运行: pip install pywin32")
            except Exception as e:
                raise Exception(f"无法解析 .doc 文件: {str(e)}")

        # Linux: 使用 antiword
        else:
            import shutil
            import subprocess

            if not shutil.which("antiword"):
                raise Exception("antiword 未安装，请在 Railway Build Command 中添加: apt-get install -y antiword")

            try:
                result = subprocess.run(
                    ["antiword", "-w", "0", os.path.abspath(file_path)],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0 and result.stdout.strip():
                    return cls._text_to_markdown(result.stdout)
                else:
                    raise Exception(f"antiword 解析失败，返回码: {result.returncode}")
            except subprocess.TimeoutExpired:
                raise Exception("antiword 解析超时")
            except Exception as e:
                raise Exception(f"无法解析 .doc 文件: {str(e)}")

    @classmethod
    def _text_to_markdown(cls, text: str) -> Tuple[str, List[dict]]:
        """将纯文本转换为带结构的 Markdown"""
        lines = text.split('\n')
        md_lines = []
        mappings = []
        current_pos = 0

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                current_pos += 1
                md_lines.append("")
                continue

            if re.match(r'^(第[一二三四五六七八九十\d]+[章节条项部]|第[一二三四五六七八九十\d]+讲)\s+', line):
                md_lines.append(f"## {line}")
            elif re.match(r'^\d+\.\s+[^\d]', line):
                cleaned = re.sub(r'^\d+\.\s+', '', line)
                md_lines.append(f"## {cleaned}")
            else:
                md_lines.append(line)

            start = current_pos
            end = current_pos + len(line)
            mappings.append({
                "page_num": i // 30 + 1,
                "content": line,
                "start_char": start,
                "end_char": end
            })
            current_pos = end + 2

        return "\n".join(md_lines), mappings

    @classmethod
    def parse_xlsx(cls, file_path: str) -> Tuple[str, List[dict]]:
        """从 Excel .xlsx 文件提取文本"""
        from openpyxl import load_workbook

        wb = load_workbook(file_path, data_only=True)
        result_parts = []
        mappings = []
        current_pos = 0

        for sheet_idx, sheet_name in enumerate(wb.sheetnames, start=1):
            sheet = wb[sheet_name]
            result_parts.append(f"## {sheet_name}\n")
            start = current_pos
            current_pos += len(f"## {sheet_name}\n")

            rows_data = []
            for row in sheet.iter_rows(values_only=True):
                row_values = [str(cell) if cell is not None else "" for cell in row]
                if any(v for v in row_values):
                    row_text = " | ".join(row_values) + " |"
                    rows_data.append(f"| {row_text} |")

                    mappings.append({
                        "page_num": sheet_idx,
                        "content": row_text,
                        "start_char": current_pos,
                        "end_char": current_pos + len(row_text)
                    })
                    current_pos += len(row_text) + 1

            if rows_data:
                col_count = len(rows_data[0].split(" | ")) if " | " in rows_data[0] else 1
                result_parts.append("| " + " | ".join(["---"] * col_count) + " |\n")
                result_parts.extend([r + "\n" for r in rows_data])
                result_parts.append("\n")

        wb.close()
        md_text = "".join(result_parts)

        return md_text, mappings

    @classmethod
    def parse_xls(cls, file_path: str) -> Tuple[str, List[dict]]:
        """从 Excel .xls 文件提取文本"""
        import xlrd

        wb = xlrd.open_workbook(file_path)
        result_parts = []
        mappings = []
        current_pos = 0

        for sheet_idx in range(wb.nsheets):
            sheet = wb.sheet_by_index(sheet_idx)
            result_parts.append(f"## {sheet.name}\n")
            start = current_pos
            current_pos += len(f"## {sheet.name}\n")

            for row_idx in range(sheet.nrows):
                row_values = []
                for col_idx in range(sheet.ncols):
                    cell = sheet.cell(row_idx, col_idx)
                    row_values.append(str(cell.value) if cell.value else "")
                if any(v for v in row_values):
                    row_text = " | ".join(row_values) + " |"
                    mappings.append({
                        "page_num": sheet_idx + 1,
                        "content": row_text,
                        "start_char": current_pos,
                        "end_char": current_pos + len(row_text)
                    })
                    current_pos += len(row_text) + 1

        md_text = "".join(result_parts)
        return md_text, mappings

    @classmethod
    def parse_file(cls, file_path: str, file_extension: str, doc_id: str = None) -> Tuple[str, List[dict]]:
        """
        根据文件扩展名调用对应解析器

        双轨分发：
        - PDF: 优先轨道A（PyMuPDF4LLM），自动 fallback 到 pdfplumber/Vision OCR
        - 图片: 轨道B（Vision OCR）

        Returns:
            tuple: (markdown格式文本, page_mappings)
        """
        if doc_id is None:
            doc_id = uuid.uuid4().hex[:12]

        ext = file_extension.lower()
        if ext == ".pdf":
            return cls.parse_pdf(file_path, doc_id)
        elif ext in [".txt", ".md"]:
            return cls.parse_txt(file_path)
        elif ext == ".docx":
            return cls.parse_docx(file_path, doc_id)
        elif ext == ".doc":
            return cls.parse_doc(file_path)
        elif ext == ".xlsx":
            return cls.parse_xlsx(file_path)
        elif ext == ".xls":
            return cls.parse_xls(file_path)
        elif ext in [".png", ".jpg", ".jpeg"]:
            return cls.parse_image(file_path)
        else:
            raise ValueError(f"不支持的文件类型: {ext}")


class RAGEngine:
    """
    RAG 引擎核心类
    使用 LangChain + Chroma 实现多表示索引
    """

    def __init__(self):
        self.embeddings = self._init_embeddings()
        self.vectorstore = self._init_vectorstore()
        self.id_key = "doc_id"
        self.retriever = self._init_retriever()

    def _init_embeddings(self):
        """初始化 Embedding 模型"""
        return DashScopeEmbeddings(
            model=settings.EMBEDDING_MODEL,
            api_key=settings.OPENAI_API_KEY if settings.OPENAI_API_KEY else "sk-mock",
            base_url=settings.OPENAI_API_BASE
        )

    def _init_vectorstore(self) -> Chroma:
        """初始化 Chroma 向量数据库"""
        os.makedirs(settings.CHROMA_DB_PATH, exist_ok=True)
        return Chroma(
            persist_directory=settings.CHROMA_DB_PATH,
            embedding_function=self.embeddings,
            collection_name="document_chunks"
        )

    def _init_retriever(self) -> MultiVectorRetriever:
        """初始化多向量检索器"""
        vectorstore = self.vectorstore
        docstore = InMemoryStore()
        retriever = MultiVectorRetriever(
            vectorstore=vectorstore,
            docstore=docstore,
            id_key=self.id_key,
            search_type="similarity",
            search_kwargs={"k": 5}
        )
        return retriever

    def process_document(
        self,
        file_path: str,
        file_extension: str,
        metadata: Optional[dict] = None,
        doc_id: Optional[str] = None
    ) -> dict:
        """
        处理文档：解析 -> 切分 -> 入库（Multi-vector Retriever）

        实现 Parent-Child 结构：
        - 母文档（完整上下文）存入 docstore
        - 子文档（检索用）存入向量数据库

        Args:
            doc_id: 可选，外部传入的文档ID（如未提供则自动生成）

        Returns:
            dict: {
                "markdown": markdown格式文本,
                "page_mappings": [{page_num, content, start_char, end_char}, ...],
                "doc_id": 文档ID,
                "status": "OK" | "WARNING",
                "verification_warnings": [...]
            }
        """
        doc_id = doc_id or str(uuid.uuid4())

        # 解析文档
        markdown_text, page_mappings = DocumentParser.parse_file(file_path, file_extension, doc_id)

        # 获取图片元数据
        from core.image_handler import get_image_records, get_image_record_markdown
        image_records = get_image_records(doc_id)

        # 追加图片引用（仅当内容中尚未包含时，如 DOCX 已内联插入）
        if image_records:
            image_refs = get_image_record_markdown(doc_id)
            if image_refs and image_refs.strip() not in markdown_text:
                # 检查是否已有图片引用内联在内容中
                existing_img_refs = re.findall(r'!\[.*?\]\(.*?\)', markdown_text)
                if not existing_img_refs:
                    markdown_text = markdown_text + "\n\n" + image_refs

        # 注入 RAG 语义增强标签到表格
        table_summaries = self._inject_table_rag_tags(markdown_text)

        # 抽取多种表示（结构、知识点等）供文档概览使用
        try:
            from core.doc_bot import get_doc_bot_v2
            doc_bot = get_doc_bot_v2()
            representations = doc_bot.extractor.extract(markdown_text, doc_id, page_mappings)
            doc_bot.vector_store.add_representations(representations)
        except Exception as e:
            print(f"表示抽取失败: {e}")
            import traceback
            traceback.print_exc()

        # 切分文档并入库
        self._split_and_index(markdown_text, doc_id, metadata, table_summaries)

        # 自校对
        warnings = self._self_verify(markdown_text, image_records)

        result = {
            "doc_id": doc_id,
            "markdown": markdown_text,
            "page_mappings": page_mappings,
            "raw_text_length": len(markdown_text),
            "image_count": len(image_records)
        }

        if warnings:
            result["status"] = "WARNING"
            result["verification_warnings"] = warnings

        return result

    def _inject_table_rag_tags(self, markdown_text: str) -> List[dict]:
        """
        Patch 4: RAG语义增强标签
        检测 Markdown 中的表格块，注入 HTML 注释形式的语义标签
        """
        table_summaries = []

        # 查找所有 Markdown 表格块
        table_pattern = re.compile(
            r'((?:^\|.*\|$\n)+)',
            re.MULTILINE
        )

        for match in table_pattern.finditer(markdown_text):
            table_block = match.group(1)
            lines = table_block.strip().split('\n')

            if len(lines) < 2:
                continue

            # 提取表头
            headers = [h.strip() for h in lines[0].strip('|').split('|')]
            # 估算行数（减去分隔线行）
            row_count = max(0, len(lines) - 2)

            # 提取首行和末行数据用于趋势分析
            data_lines = [l for l in lines if not re.match(r'^\|[\s\-:|]+\|$', l.strip()) and '|' in l]
            first_row = []
            last_row = []
            if len(data_lines) > 0:
                first_row = [c.strip() for c in data_lines[0].strip('|').split('|')]
            if len(data_lines) > 1:
                last_row = [c.strip() for c in data_lines[-1].strip('|').split('|')]

            # 生成趋势描述
            trend = ""
            if first_row and last_row and len(first_row) > 1 and len(last_row) > 1:
                try:
                    first_num = float(first_row[-1].replace(',', '').replace('%', ''))
                    last_num = float(last_row[-1].replace(',', '').replace('%', ''))
                    if last_num > first_num:
                        trend = f"增长趋势: {first_row[0]}→{last_row[0]} 末值上升"
                    elif last_num < first_num:
                        trend = f"下降趋势: {first_row[0]}→{last_row[0]} 末值下降"
                except (ValueError, IndexError):
                    trend = ""

            # 生成 HTML 版本
            html_lines = ["<table>"]
            html_lines.append("  <tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>")
            for line in data_lines[1:] if len(data_lines) > 1 else data_lines:
                cells = [c.strip() for c in line.strip('|').split('|')]
                html_lines.append("  <tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            html_lines.append("</table>")
            table_html = "\n".join(html_lines)

            # 生成结构化 JSON
            table_json = json.dumps({
                "headers": headers,
                "rows": [
                    [c.strip() for c in l.strip('|').split('|')]
                    for l in data_lines
                ],
                "row_count": row_count,
                "context": trend,
                "format": "markdown_table"
            }, ensure_ascii=False)

            # 生成 RAG 语义增强标签（HTML 注释，不影响渲染）
            topic = headers[0] if headers else "未知"
            rag_tag = (
                f"<!-- RAG_TABLE_SUMMARY: 主题=\"{topic}\"; "
                f"表头=[{', '.join(headers)}]; "
                f"趋势=\"{trend}\"; "
                f"行数={row_count} -->"
            )

            # 记录表格信息
            table_summaries.append({
                "position": match.start(),
                "table_html": table_html,
                "table_json": table_json,
                "rag_tag": rag_tag
            })

        # 从后向前注入标签（避免位置偏移）
        for table_info in reversed(table_summaries):
            pos = table_info["position"]
            markdown_text = markdown_text[:pos] + table_info["rag_tag"] + "\n" + markdown_text[pos:]

        return table_summaries

    def _split_and_index(self, markdown_text: str, doc_id: str, metadata: Optional[dict] = None, table_summaries: Optional[List[dict]] = None) -> None:
        """
        将文档切分为母文档和子文档，并分别入库

        - 母文档（Parent）：完整上下文，存入 docstore
        - 子文档（Child）：检索用小块，存入向量数据库
        """
        parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=100,
            separators=["\n\n", "\n", "## ", "### ", "# ", "."]
        )
        child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=400,
            chunk_overlap=50,
            separators=["\n\n", "\n", "## ", "### ", "# "]
        )

        parent_docs = parent_splitter.create_documents([markdown_text])

        docstore_kv_pairs = []
        child_docs_to_add = []

        # 构建表格 metadata 索引（用于快速查找包含表格的母文档）
        table_metadata = {}
        if table_summaries:
            table_metadata["table_count"] = len(table_summaries)
            table_metadata["table_html"] = "\n\n".join(t["table_html"] for t in table_summaries)
            table_metadata["table_json"] = "\n\n".join(t["table_json"] for t in table_summaries)
            table_metadata["table_summary"] = "\n".join(t["rag_tag"] for t in table_summaries)

        for parent_doc in parent_docs:
            parent_id = str(uuid.uuid4())

            parent_doc.metadata["parent_id"] = parent_id
            parent_doc.metadata["doc_id"] = doc_id
            if metadata:
                parent_doc.metadata.update(metadata)
            # 注入表格 metadata
            if table_metadata:
                parent_doc.metadata.update(table_metadata)

            docstore_kv_pairs.append((parent_id, parent_doc))

            child_docs = child_splitter.split_documents([parent_doc])

            for child_doc in child_docs:
                # 过滤空文本块，防止 DashScope 400 错误
                if not child_doc.page_content or not child_doc.page_content.strip():
                    continue
                child_doc.metadata["parent_id"] = parent_id
                child_doc.metadata["doc_id"] = doc_id
                if metadata:
                    child_doc.metadata.update(metadata)
                if table_metadata:
                    child_doc.metadata.update(table_metadata)
                child_docs_to_add.append(child_doc)

        if child_docs_to_add:
            self.vectorstore.add_documents(child_docs_to_add)
            print(f"[RAG] Added {len(child_docs_to_add)} child docs to vectorstore")

        if docstore_kv_pairs:
            self.retriever.docstore.mset(docstore_kv_pairs)
            print(f"[RAG] Added {len(docstore_kv_pairs)} parent docs to docstore")

    def _self_verify(self, markdown: str, image_records: list) -> List[str]:
        """
        Patch 5: Asset 数量自校对
        对比提取的 assets 与 Markdown 中的占位符数量
        """
        warnings = []

        # 统计图片占位符
        md_image_refs = re.findall(r'!\[.*?\]\((.*?)\)', markdown)
        expected_images = len(image_records)

        if expected_images > 0 and len(md_image_refs) != expected_images:
            missing_ids = [img.image_id for img in image_records
                         if not any(img.stored_path in ref for ref in md_image_refs)]
            warnings.append(
                f"IMAGE_MISMATCH: 提取了{expected_images}张图片，"
                f"但Markdown中只有{len(md_image_refs)}个占位符。"
                f"缺失: {missing_ids}"
            )

        # 统计表格
        md_tables = re.findall(r'\|.*?\|.*?\n\|[-:|]+\|', markdown)

        return warnings

    def similarity_search(self, query: str, k: int = 5) -> list[Document]:
        """执行相似度搜索"""
        return self.vectorstore.similarity_search(query, k=k)

    def retrieve_with_expansion(self, query: str, k: int = 3) -> list[Document]:
        """检索并扩展上下文"""
        sub_docs = self.vectorstore.similarity_search(query, k=k)

        parent_ids = set()
        for doc in sub_docs:
            doc_id = doc.metadata.get("doc_id")
            if doc_id:
                parent_ids.add(doc_id)

        all_docs = self.vectorstore.get()
        parent_docs = []

        for doc in all_docs["documents"]:
            meta = all_docs["metadatas"][all_docs["documents"].index(doc)]
            if meta.get("doc_id") in parent_ids and "parent_id" not in meta:
                parent_docs.append(Document(page_content=doc, metadata=meta))

        if not parent_docs:
            return sub_docs

        return parent_docs

    def get_document_by_id(self, doc_id: str) -> list[Document]:
        """根据 doc_id 获取文档的所有块"""
        return self.vectorstore.get(where={"doc_id": doc_id})


# 全局 RAG 引擎实例
_rag_engine: Optional[RAGEngine] = None


def get_rag_engine() -> RAGEngine:
    """获取 RAG 引擎单例"""
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = RAGEngine()
    return _rag_engine
