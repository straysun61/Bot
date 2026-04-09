# 文档处理 Bot 架构与技术栈概览

本文档详细描述了当前文档处理 Bot 所采用的系统架构、数据流向以及相关的技术选型，并侧重点明了底层的 RAG (检索增强生成)、多表示索引 (Multi-representation Indexing) 以及嵌入 (Embedding) 的底层设计机制。

## 1. 核心技术栈 (Technology Stack)

> [!TIP]
> 我们的技术选型主要针对 **高性能并发场景** 和 **高精度 RAG 检索引擎** 进行设计。

### 后端框架与基础组件
- **RESTful API 框架**: FastAPI (天然支持异步，高性能)。
- **持久化层**: Python SQLAlchemy + 关系型数据库 (MySQL/PgSQL) 用于管理用户和鉴权。

### 鉴权模块 (Authentication / Security)
- **双重拦截层**:基于 JWT 的 `Bearer Token` 以及供下游系统集成的 `x-api-key`。

### **核心 RAG 组件层 (AI & Embedding)**
- **Embedding 多核引擎**: `BGE-m3` 或 `OpenAI text-embedding-3-small/large`。负责将文本转化为连续高维稠密向量。
- **高阶 RAG 与索引管理**: LangChain / LlamaIndex 生态。专门使用其 Multi-Vector Retriever (多向量检索器) 来支撑多表示索引。
- **高维向量数据库**: `Milvus` 或 `Qdrant`（支持百亿级向量的高效近似最近邻算法 HNSW）。

---

## 2. 逻辑分层与系统拓扑

整个系统由前端接入至后台异步的高精度 RAG 处理：

```mermaid
graph TD
    %% 客户端层
    Client[客户端/系统代理] -- "x-api-key 或 JWT" --> LoadBalancer((API 接口网关))
    
    subgraph FastAPI 后端
        LoadBalancer --> AuthLayer(核心鉴权层)
        AuthLayer -- 放行 --> Routers[路由分发系统]
    end
    
    %% RAG 文档特征采集与索引分支
    Routers -- "1. 上传文档" --> IngestionWorker(后台多表示拆分器)
    IngestionWorker -- "提取/总结生成" --> Summary[文档摘要表达 (Summary)]
    IngestionWorker -- "精准分片映射" --> Chunks[原文档切片 (Chunks)]
    
    Summary -- "模型生成向量" --> EmbeddingEngine[大语言嵌入模型 Embedding]
    Chunks -- "生成原文本映射" --> DocStore[(结构化KV文档库 \n Redis/MongoDB)]
    
    EmbeddingEngine -- "向量结果" --> VectorDB[(向量数据库 \n Chroma/Milvus)]
    
    %% Q&A 问答生成分支
    Routers -- "2. 发起查询" --> RAG_Pipeline(RAG 知识检索流水线)
    RAG_Pipeline -- "查询 Embedding" --> VectorDB
    VectorDB -- "命中高相关度摘要" --> RAG_Pipeline
    RAG_Pipeline -- "通过 ID 映射到 KV库溯源" --> DocStore
    DocStore -- "提送最全量详细语料" --> Generator[LLM 答案生成器]
    Generator -- "合并上下文生成答案" --> Client
```

---

## 3. 深入 RAG 与多表示索引机制体现 (Deep Dive)

为了解决传统单纯“切片(Chunk) -> 匹配 -> 回答”在处理复杂长文档时**容易丢失全局上下文和颗粒度控制不良**的问题，本 Bot 强依赖了**多表示索引 (Multi-Representation Indexing)** 与**前沿的 Embedding 策略**。

### A. 什么是“多表示索引”在本系统中的体现？
在本系统中，一份被上传的文档不会被简单地暴力切成文字块存入向量库。它使用的是 **母子文档检索 (Parent-Child Retriever)** 结合 **总结检索 (Summary-based Retrieval)** 的策略：

1. **分离存储与检索 (Decoupling)**：
   - 系统将原始大块文本（如一整个篇章，称为 Parent Document）原封不动存放在成本较低的 Key-Value 数据库（如 MongoDB/Redis）中，或者直接借用 LangChain 的 `InMemoryStore`/`RedisStore`。
   - 随后，大模型或者算法会在后台为这个长文本生成**多种不同的精简“表示” (Representations)**，例如：“该长文档的核心摘要 (Summary)” 以及 “将该文档细切成更小、语义干瘪但极精准的短语块 (Child Chunks)”。
2. **向量与关联 (Mapping)**：
   - **嵌入 (Embedding)** 全面接管这些“摘要”和“短特征块”，将它们变成向量打入 `Milvus`/`Chroma` 中。
   - 每个切片向量结构都会带有一个明确的 `doc_id` 标签，指向 KV 库中那段宏大、完整的母段落 (Parent Document)。

### B. 嵌入算法流向 (Embedding Flow)
1. **统一的高维映射空间**: 当文档被转化为“多表示”后，我们通过诸如 `text-embedding-3-small`，在 1536 维的数学空间中构建词汇上下文距离的分布。
2. **查询时双路 Embedding**: 用户的搜索提问 Query 会被相同的 Embedding 模型转化为向量，进而进行余弦相似度计算 (Cosine Similarity Computation)。

### C. RAG 对话检索生成全生命周期 (The RAG Pipeline)
当系统被调用 `/api/v1/chat/completions` 时，RAG 链路启动：
1. **检索阶段 (Retrieve)**：向量数据库对比用户的 Query 向量，发现在茫茫多的“表示”中，命中了一篇复杂报告的**浓缩总结向量**，又命中了报告第三页的一个**高粒度细节短句向量**。
2. **溯源映射阶段 (Map & Expand)**：不同于传统 RAG 直接把这个“总结”和“短句”甩给大模型回答（这会导致大模型因为细节太少而出现幻觉）。在**多表示检索机制**的魔法下，API 层利用它们的 `doc_id` 锚点返回去 KV 存储库中，提取出它们**背后所代表的那一整页甚至那一整篇的最原汁原味的宏大语境内容**。
3. **增强与生成 (Augment & Generate)**: 我们将最丰满、上下文完备的母级语料作为背景上下文 (Context) 塞入用户的 Prompt 中，调用强大的对话大模型（LLM）。
4. **高质量输出**: 大模型不再是盲人摸象，而是站在全貌上基于精准片段进行了精确提取，向用户流式反馈高质量回答。
