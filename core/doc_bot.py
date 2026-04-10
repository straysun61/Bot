"""
文档处理机器人 - 多表示抽取 + 多表示索引 + 真实Embedding
"""
import os
import re
import hashlib
import httpx
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from core.config import settings


class DashScopeEmbeddings(Embeddings):
    """DashScope (阿里云百炼) Embedding 实现"""

    def __init__(self, model: str = "text-embedding-v3", api_key: str = None, base_url: str = None):
        self.model = model
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.base_url = base_url or settings.OPENAI_API_BASE

    def _call_api(self, texts: List[str]) -> List[List[float]]:
        """调用 DashScope embedding API"""
        import time
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

        start = time.time()
        response = httpx.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={"model": self.model, "input": texts},
            timeout=30.0
        )
        elapsed = time.time() - start
        print(f"[HTTPX] API call took {elapsed:.2f}s for {len(texts)} texts")
        response.raise_for_status()
        result = response.json()
        return [item["embedding"] for item in result["data"]]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入文档"""
        return self._call_api(texts)

    def embed_query(self, text: str) -> List[float]:
        """嵌入单个查询"""
        return self._call_api([text])[0]


class RepresentationType(Enum):
    """表示类型"""
    FULL_TEXT = "full_text"
    CHUNK = "chunk"
    STRUCTURE = "structure"
    KNOWLEDGE = "knowledge"


@dataclass
class Representation:
    """文档表示"""
    rep_type: RepresentationType
    content: str
    metadata: Dict[str, Any]


class MultiRepresentationExtractor:
    """
    多表示抽取器

    从 Markdown 文档中抽取 4 种表示，并追踪页码信息
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def extract(self, md_content: str, doc_id: str, page_mappings: List[dict] = None) -> List[Representation]:
        """
        从 Markdown 文档中抽取多种表示

        Args:
            md_content: Markdown 格式的文档内容
            doc_id: 文档ID
            page_mappings: 页码映射列表 [{page_num, content, start_char, end_char}, ...]

        Returns:
            List of Representation
        """
        self.page_mappings = page_mappings or []
        representations = []

        # 1. 全文表示
        full_text_rep = self._extract_full_text(md_content, doc_id)
        representations.append(full_text_rep)

        # 2. 分块表示
        chunk_reps = self._extract_chunks(md_content, doc_id)
        representations.extend(chunk_reps)

        # 3. 结构表示
        structure_reps = self._extract_structure(md_content, doc_id)
        representations.extend(structure_reps)

        # 4. 知识点表示
        knowledge_reps = self._extract_knowledge(md_content, doc_id)
        representations.extend(knowledge_reps)

        return representations

    def _find_page_for_position(self, char_position: int) -> int:
        """根据字符位置查找对应的页码"""
        for mapping in self.page_mappings:
            if mapping["start_char"] <= char_position < mapping["end_char"]:
                return mapping["page_num"]
        # 如果没找到，返回估算的页码
        if self.page_mappings:
            return self.page_mappings[-1]["page_num"]
        return 1

    def _extract_full_text(self, md_content: str, doc_id: str) -> Representation:
        """抽取全文表示：摘要 + 关键词"""
        md_clean = re.sub(r'\n{3,}', '\n\n', md_content.strip())

        # 提取标题
        headings = re.findall(r'^(#{1,6})\s+(.+)$', md_content, re.MULTILINE)

        if not headings:
            numbered_sections = re.findall(r'^(\d+)\s*\n(.+)$', md_content, re.MULTILINE)
            title_summary = " | ".join([s[1] for s in numbered_sections[:5]])
            section_count = len(numbered_sections)
        else:
            title_summary = " | ".join([h[1] for h in headings[:5]])
            section_count = len(headings)

        # 关键词
        words = re.findall(r'[\w]{2,}', md_content.lower())
        word_freq = {}
        stopwords = {'的', '是', '在', '和', '了', '是', '有', '我', '你', '他', '这', '那', '个', '与', '及', '或', '等', '为', '以', '及', '于', '上', '下', '中', '可以', '这个', '一个', '以及', '通过', '进行', '其中'}
        for word in words:
            if word not in stopwords and len(word) > 1:
                word_freq[word] = word_freq.get(word, 0) + 1

        top_keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
        keywords = ", ".join([w[0] for w in top_keywords])

        # 摘要
        lines = [l.strip() for l in md_content.split('\n') if l.strip() and len(l.strip()) > 5]
        preview_text = " ".join(lines[:3])[:200]
        page_num = self._find_page_for_position(0)

        summary = f"文档包含 {section_count} 个章节，{len(words)} 个词汇。"
        if preview_text:
            summary += f"\n\n内容预览：{preview_text}..."

        return Representation(
            rep_type=RepresentationType.FULL_TEXT,
            content=f"# 文档摘要\n\n{summary}\n\n# 关键词\n{keywords}",
            metadata={
                "doc_id": doc_id,
                "rep_type": "full_text",
                "title_summary": title_summary,
                "keywords": [w[0] for w in top_keywords],
                "section_count": section_count,
                "page_num": page_num,
                "start_char": 0,
                "end_char": len(md_content)
            }
        )

    def _extract_chunks(self, md_content: str, doc_id: str) -> List[Representation]:
        """抽取分块表示：标准 chunk，带页码"""
        representations = []

        # 按 ## 标题分割
        sections = re.split(r'\n(?=##\s)', md_content)

        chunk_idx = 0
        for sec_idx, section in enumerate(sections):
            section = section.strip()
            if not section:
                continue

            # 提取标题
            title_match = re.match(r'^(#{1,6})\s+(.+)$', section, re.MULTILINE)
            heading = title_match.group(2) if title_match else f"Section {sec_idx + 1}"
            heading_level = len(title_match.group(1)) if title_match else 1

            # 找到这段内容在原文档中的起始位置
            section_start = md_content.find(section[:50])
            page_num = self._find_page_for_position(section_start if section_start >= 0 else 0)

            # 如果太长，按段落分割
            if len(section) > self.chunk_size:
                paragraphs = re.split(r'\n\n+', section)
                current_chunk = ""

                for para in paragraphs:
                    para = para.strip()
                    if not para:
                        continue

                    if len(current_chunk) + len(para) > self.chunk_size and current_chunk:
                        chunk_start = md_content.find(current_chunk[:50])
                        chunk_page = self._find_page_for_position(chunk_start if chunk_start >= 0 else 0)

                        representations.append(Representation(
                            rep_type=RepresentationType.CHUNK,
                            content=current_chunk.strip(),
                            metadata={
                                "doc_id": doc_id,
                                "rep_type": "chunk",
                                "chunk_id": f"{doc_id}_chunk_{chunk_idx}",
                                "title": heading,
                                "heading_level": heading_level,
                                "chunk_index": chunk_idx,
                                "parent_section": sec_idx,
                                "page_num": chunk_page,
                                "char_count": len(current_chunk)
                            }
                        ))
                        chunk_idx += 1
                        current_chunk = para
                    else:
                        current_chunk += ("\n\n" + para) if current_chunk else para

                if current_chunk.strip():
                    chunk_start = md_content.find(current_chunk[:50])
                    chunk_page = self._find_page_for_position(chunk_start if chunk_start >= 0 else 0)

                    representations.append(Representation(
                        rep_type=RepresentationType.CHUNK,
                        content=current_chunk.strip(),
                        metadata={
                            "doc_id": doc_id,
                            "rep_type": "chunk",
                            "chunk_id": f"{doc_id}_chunk_{chunk_idx}",
                            "title": heading,
                            "heading_level": heading_level,
                            "chunk_index": chunk_idx,
                            "parent_section": sec_idx,
                            "page_num": chunk_page,
                            "char_count": len(current_chunk)
                        }
                    ))
                    chunk_idx += 1
            else:
                representations.append(Representation(
                    rep_type=RepresentationType.CHUNK,
                    content=section,
                    metadata={
                        "doc_id": doc_id,
                        "rep_type": "chunk",
                        "chunk_id": f"{doc_id}_chunk_{chunk_idx}",
                        "title": heading,
                        "heading_level": heading_level,
                        "chunk_index": chunk_idx,
                        "parent_section": sec_idx,
                        "page_num": page_num,
                        "char_count": len(section)
                    }
                ))
                chunk_idx += 1

        return representations

    def _extract_structure(self, md_content: str, doc_id: str) -> List[Representation]:
        """抽取结构表示：标题层级、目录、表格"""
        representations = []

        # 1. 提取目录
        headings = re.findall(r'^(#{1,6})\s+(.+)$', md_content, re.MULTILINE)
        toc_lines = []
        heading_tree = []

        for h in headings:
            level = len(h[0])
            indent = "  " * (level - 1)
            toc_lines.append(f"{indent}- {h[1]}")
            heading_tree.append({"level": level, "title": h[1]})

        if not headings:
            # 匹配格式如 "1.1 在OEM中创建..." 或 "任务1：..." 或 "三、实验内容"
            numbered_sections = re.findall(r'^(\d+[.、：:]\s*[^\n]{0,80})', md_content, re.MULTILINE)
            for sec in numbered_sections:
                sec = sec.strip()
                if len(sec) > 5:  # 过滤太短的匹配
                    toc_lines.append(f"- {sec}")
                    heading_tree.append({"level": 1, "title": sec, "number": ""})

        if toc_lines:
            page_num = self._find_page_for_position(0)
            representations.append(Representation(
                rep_type=RepresentationType.STRUCTURE,
                content="# 目录结构\n\n" + "\n".join(toc_lines),
                metadata={
                    "doc_id": doc_id,
                    "rep_type": "structure",
                    "structure_type": "toc",
                    "heading_tree": heading_tree,
                    "page_num": page_num
                }
            ))

        # 2. 提取表格
        tables = re.findall(r'\|.+\|\n\|[-| :]+\|\n(?:\|.+\|\n?)+', md_content)
        if tables:
            table_summary = f"文档包含 {len(tables)} 个表格：\n\n"
            for i, table in enumerate(tables[:5]):
                lines = table.strip().split('\n')
                if len(lines) >= 2:
                    header = lines[0]
                    table_summary += f"### 表格 {i+1}\n{header}\n\n"

            # 找到表格在文档中的位置
            first_table_pos = md_content.find(tables[0][:50]) if tables else 0
            page_num = self._find_page_for_position(first_table_pos if first_table_pos >= 0 else 0)

            representations.append(Representation(
                rep_type=RepresentationType.STRUCTURE,
                content=table_summary,
                metadata={
                    "doc_id": doc_id,
                    "rep_type": "structure",
                    "structure_type": "tables",
                    "table_count": len(tables),
                    "page_num": page_num
                }
            ))

        return representations

    def _extract_knowledge(self, md_content: str, doc_id: str) -> List[Representation]:
        """抽取知识点表示：关键结论、术语"""
        representations = []

        # 1. 提取结论性语句
        conclusion_keywords = ['因此', '所以', '结论', '总之', '表明', '证明', '发现', '总结', '得出', '说明', '必须', '要求', '不得']
        sentences = re.split(r'[。！？\n]+', md_content)
        conclusions = []
        conclusion_positions = []

        for sent in sentences:
            sent = sent.strip()
            if not sent or len(sent) < 10:
                continue
            for kw in conclusion_keywords:
                if kw in sent:
                    conclusions.append(sent)
                    pos = md_content.find(sent)
                    conclusion_positions.append(pos if pos >= 0 else 0)
                    break

        if conclusions:
            # 获取结论所在页码
            pages = [self._find_page_for_position(pos) for pos in conclusion_positions]
            page_num = max(pages) if pages else 1

            representations.append(Representation(
                rep_type=RepresentationType.KNOWLEDGE,
                content="# 关键结论\n\n" + "\n\n".join([f"- {c}" for c in conclusions[:10]]),
                metadata={
                    "doc_id": doc_id,
                    "rep_type": "knowledge",
                    "knowledge_type": "conclusions",
                    "count": len(conclusions),
                    "page_num": page_num
                }
            ))

        # 2. 提取术语
        terms = re.findall(r'[`"\"]([^`"\"]+)[`"\"]', md_content)
        if terms:
            representations.append(Representation(
                rep_type=RepresentationType.KNOWLEDGE,
                content="# 术语列表\n\n" + "\n\n".join([f"- **{t}**" for t in terms[:20]]),
                metadata={
                    "doc_id": doc_id,
                    "rep_type": "knowledge",
                    "knowledge_type": "terms",
                    "terms": terms[:20],
                    "page_num": 1
                }
            ))

        # 3. 提取要点
        list_items = re.findall(r'^\s*[-*+]\s+(.+)$', md_content, re.MULTILINE)
        key_lines = []
        for line in md_content.split('\n'):
            line = line.strip()
            if re.match(r'^.+[：:]\s*.+\d+.+$', line) and len(line) < 100:
                key_lines.append(line)

        if list_items or key_lines:
            content_parts = []
            if list_items:
                content_parts.append("## 要点列表\n" + "\n".join([f"- {item}" for item in list_items[:15]]))
            if key_lines:
                content_parts.append("## 关键信息\n" + "\n".join([f"- {line}" for line in key_lines[:10]]))

            representations.append(Representation(
                rep_type=RepresentationType.KNOWLEDGE,
                content="# 关键要点\n\n" + "\n\n".join(content_parts),
                metadata={
                    "doc_id": doc_id,
                    "rep_type": "knowledge",
                    "knowledge_type": "key_points",
                    "count": len(list_items) + len(key_lines),
                    "page_num": 1
                }
            ))

        return representations


class RealEmbeddingStore:
    """
    真实 Embedding 向量存储

    使用 OpenAI Embedding API 生成真实向量
    """

    def __init__(self):
        self._embeddings = None
        self._init_embeddings()
        # 存储: {chunk_id: {"doc": Document, "embedding": List[float]}}
        self.store: Dict[str, Dict] = {}

    def _init_embeddings(self):
        """初始化 Embedding 模型"""
        try:
            self._embeddings = DashScopeEmbeddings(
                model=settings.EMBEDDING_MODEL,
                api_key=settings.OPENAI_API_KEY if settings.OPENAI_API_KEY else "sk-mock",
                base_url=settings.OPENAI_API_BASE
            )
        except Exception as e:
            print(f"Embedding 初始化失败: {e}，将使用模拟向量")
            self._embeddings = None

    def _get_embedding(self, text: str) -> List[float]:
        """获取文本的真实 embedding 向量"""
        if self._embeddings is None:
            # 回退到 MD5 模拟
            hash_bytes = hashlib.md5(text.encode()).digest()
            return [float(b) / 255.0 for b in hash_bytes[:16]] * 8

        try:
            import threading
            result = [None]
            error = [None]

            def embed():
                try:
                    result[0] = self._embeddings.embed_query(text)
                except Exception as e:
                    error[0] = e

            t = threading.Thread(target=embed)
            t.daemon = True
            t.start()
            t.join(timeout=5)  # 5秒超时

            if t.is_alive():
                # 超时，使用模拟
                print(f"Embedding timeout, using mock")
                hash_bytes = hashlib.md5(text.encode()).digest()
                return [float(b) / 255.0 for b in hash_bytes[:16]] * 8
            elif error[0]:
                print(f"Embedding error: {error[0]}, using mock")
                hash_bytes = hashlib.md5(text.encode()).digest()
                return [float(b) / 255.0 for b in hash_bytes[:16]] * 8
            else:
                return result[0]
        except Exception as e:
            print(f"Embedding 生成失败: {e}，使用模拟向量")
            hash_bytes = hashlib.md5(text.encode()).digest()
            return [float(b) / 255.0 for b in hash_bytes[:16]] * 8

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        """计算余弦相似度"""
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = sum(a * a for a in v1) ** 0.5
        norm2 = sum(b * b for b in v2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    def add_representations(self, representations: List[Representation]) -> None:
        """添加表示到存储，生成真实 embedding - 分批优化版本"""
        if not representations:
            return

        import time
        print(f"[DEBUG] add_representations: starting with {len(representations)} items")

        # 准备所有表示的数据
        items = []
        for rep in representations:
            chunk_id = rep.metadata.get("chunk_id", f"{rep.metadata['doc_id']}_{rep.rep_type.value}")
            doc = Document(page_content=rep.content, metadata=rep.metadata)
            items.append({
                "chunk_id": chunk_id,
                "doc": doc,
                "rep": rep,
                "content": rep.content
            })

        # 检查是否支持批量 embedding
        if self._embeddings is not None and hasattr(self._embeddings, 'embed_documents'):
            # 使用分批批量 embedding（每批最多10个，避免 400 错误）
            batch_size = 10
            total_time = 0
            for batch_start in range(0, len(items), batch_size):
                batch_end = min(batch_start + batch_size, len(items))
                batch_items = items[batch_start:batch_end]
                batch_contents = [item["content"] for item in batch_items]
                batch_num = batch_start // batch_size + 1

                batch_start_time = time.time()
                try:
                    embeddings = self._embeddings.embed_documents(batch_contents)
                    batch_time = time.time() - batch_start_time
                    total_time += batch_time
                    print(f"[DEBUG] Batch {batch_num}: SUCCESS in {batch_time:.2f}s ({len(batch_items)} items)")
                    for i, item in enumerate(batch_items):
                        self.store[item["chunk_id"]] = {
                            "doc": item["doc"],
                            "embedding": embeddings[i],
                            "rep_type": item["rep"].rep_type
                        }
                except Exception as e:
                    batch_time = time.time() - batch_start_time
                    total_time += batch_time
                    print(f"[DEBUG] Batch {batch_num}: FAILED in {batch_time:.2f}s - {e}")
                    print(f"[DEBUG] Falling back to individual for this batch")
                    # 回退到逐个处理这一批
                    for j, item in enumerate(batch_items):
                        item_start = time.time()
                        try:
                            embedding = self._get_embedding(item["content"])
                            item_time = time.time() - item_start
                            print(f"[DEBUG]   Item {j}: SUCCESS in {item_time:.2f}s")
                        except Exception as e2:
                            item_time = time.time() - item_start
                            print(f"[DEBUG]   Item {j}: FAILED in {item_time:.2f}s - {e2}")
                            # 最后 fallback: 使用 MD5 mock
                            hash_bytes = hashlib.md5(item["content"].encode()).digest()
                            embedding = [float(b) / 255.0 for b in hash_bytes[:16]] * 8
                        self.store[item["chunk_id"]] = {
                            "doc": item["doc"],
                            "embedding": embedding,
                            "rep_type": item["rep"].rep_type
                        }
            print(f"[DEBUG] add_representations: TOTAL TIME = {total_time:.2f}s")
        else:
            # 回退到逐个处理
            print(f"[DEBUG] No batch embedding support, using individual")
            for item in items:
                embedding = self._get_embedding(item["content"])
                self.store[item["chunk_id"]] = {
                    "doc": item["doc"],
                    "embedding": embedding,
                    "rep_type": item["rep"].rep_type
                }

    def search(
        self,
        query: str,
        rep_types: Optional[List[RepresentationType]] = None,
        doc_id: Optional[str] = None,
        k: int = 5
    ) -> List[Tuple[Document, float, RepresentationType]]:
        """
        多表示搜索

        Returns:
            (文档, 相似度分数, 表示类型) 列表
        """
        query_embedding = self._get_embedding(query)
        results = []

        for chunk_id, data in self.store.items():
            doc = data["doc"]

            # 按文档过滤
            if doc_id and doc.metadata.get("doc_id") != doc_id:
                continue

            # 按类型过滤
            if rep_types and data["rep_type"] not in rep_types:
                continue

            # 计算相似度
            similarity = self._cosine_similarity(query_embedding, data["embedding"])
            results.append((doc, similarity, data["rep_type"]))

        # 按相似度排序
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]

    def get_by_doc(self, doc_id: str) -> Dict[RepresentationType, List[Document]]:
        """获取某个文档的所有表示"""
        result = {}
        for data in self.store.values():
            doc = data["doc"]
            if doc.metadata.get("doc_id") == doc_id:
                rep_type = data["rep_type"]
                if rep_type not in result:
                    result[rep_type] = []
                result[rep_type].append(doc)
        return result

    def get_embedding_dimension(self) -> int:
        """获取向量维度"""
        if self.store:
            first_embedding = next(iter(self.store.values()))["embedding"]
            return len(first_embedding)
        return 0


class DocBotV2:
    """
    文档处理机器人 V2

    功能：
    1. 多表示抽取（4种表示），带页码追踪
    2. 真实 Embedding 向量存储
    3. 按表示类型查询
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.extractor = MultiRepresentationExtractor(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        self.vector_store = RealEmbeddingStore()

    def process_single_pdf(
        self,
        doc_id: str,
        md_content: str,
        page_mappings: List[dict] = None
    ) -> dict:
        """
        处理单个文档：多表示抽取 + 真实 Embedding 索引

        Args:
            doc_id: 文档ID
            md_content: Markdown 格式的文档内容
            page_mappings: 页码映射列表

        Returns:
            处理结果摘要
        """
        # 1. 多表示抽取（带页码）
        representations = self.extractor.extract(md_content, doc_id, page_mappings)

        # 2. 存入向量库（生成真实 embedding）
        self.vector_store.add_representations(representations)

        # 3. 按类型统计
        type_counts = {}
        for rep in representations:
            rep_type = rep.rep_type.value
            type_counts[rep_type] = type_counts.get(rep_type, 0) + 1

        return {
            "doc_id": doc_id,
            "total_representations": len(representations),
            "by_type": type_counts,
            "embedding_dimension": self.vector_store.get_embedding_dimension(),
            "samples": [
                {
                    "rep_type": rep.rep_type.value,
                    "content_preview": rep.content[:150] + "..." if len(rep.content) > 150 else rep.content,
                    "metadata": {
                        k: v for k, v in rep.metadata.items()
                        if k in ["page_num", "chunk_id", "title", "rep_type"]
                    }
                }
                for rep in representations[:5]
            ]
        }

    def rag_query(
        self,
        question: str,
        doc_id: Optional[str] = None,
        rep_types: Optional[List[str]] = None,
        k: int = 5
    ) -> dict:
        """
        多表示 RAG 查询

        Args:
            question: 查询问题
            doc_id: 可选，限定查询范围
            rep_types: 可选，限定表示类型
            k: 召回数量

        Returns:
            召回结果
        """
        types_to_search = None
        if rep_types:
            types_to_search = [RepresentationType(rt) for rt in rep_types]

        results = self.vector_store.search(
            query=question,
            rep_types=types_to_search,
            doc_id=doc_id,
            k=k
        )

        return {
            "question": question,
            "doc_id": doc_id,
            "rep_types_filter": rep_types,
            "total_results": len(results),
            "results": [
                {
                    "content": doc.page_content,
                    "similarity": float(score),
                    "rep_type": rep_type.value,
                    "chunk_id": doc.metadata.get("chunk_id"),
                    "title": doc.metadata.get("title", ""),
                    "page_num": doc.metadata.get("page_num"),
                    "metadata": {
                        k: v for k, v in doc.metadata.items()
                        if k not in ["doc_id", "chunk_id", "title"]
                    }
                }
                for doc, score, rep_type in results
            ]
        }

    def get_doc_representations(self, doc_id: str) -> dict:
        """获取某个文档的所有表示"""
        reps_by_type = self.vector_store.get_by_doc(doc_id)

        return {
            "doc_id": doc_id,
            "representations": {
                rep_type.value: [
                    {
                        "chunk_id": doc.metadata.get("chunk_id"),
                        "content_preview": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
                        "page_num": doc.metadata.get("page_num"),
                        "metadata": {k: v for k, v in doc.metadata.items() if k not in ["doc_id", "chunk_id"]}
                    }
                    for doc in docs
                ]
                for rep_type, docs in reps_by_type.items()
            }
        }


# 全局单例
_doc_bot_v2: Optional[DocBotV2] = None


def get_doc_bot_v2() -> DocBotV2:
    """获取 DocBotV2 单例"""
    global _doc_bot_v2
    if _doc_bot_v2 is None:
        _doc_bot_v2 = DocBotV2()
    return _doc_bot_v2
