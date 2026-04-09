# 文档处理 Bot 系统架构图册 (Architecture Diagrams)

本文档为您提供了全面且精细的系统架构与数据流图表。您可以使用支持 Mermaid 渲染的 Markdown 编辑器（如 GitHub, VS Code, Obsidian 等）直接为您呈现可视图形。

---

## 1. 系统总体逻辑架构图 (System Architecture Topology)

本图展示了系统总体的分层架构：从终端用户的请求发起到核心 API 拦截、分发，直至最底层的异步处理、存储引擎与 LLM 无缝衔接。

```mermaid
flowchart TD
    %% 用户终端与网关
    ClientA[Web 前端门户] --> |"携带 JWT Access Token"| APIGateway
    ClientB[第三方企业系统] --> |"携带 API-Key"| APIGateway
    
    subgraph FastAPI 核心网关与调度层
        APIGateway(API 入口 / Load Balancer) --> SecDetector{安全鉴权依赖\n(Dependencies)}
        
        SecDetector -- 失败 --> 401[返回 HTTP 401]
        SecDetector -- 成功 --> Router[业务路由聚合]
        
        %% 核心路由模块
        Router -- "/auth" --> AuthRC(凭证颁发服务)
        Router -- "/documents" --> DocRC(上传处理服务)
        Router -- "/chat" --> ChatRC(问答对答服务)
    end
    
    subgraph 关系型持久化存储 (Meta Store)
        AuthRC <--> SQLDB[(MySQL / PostgreSQL)]
        SQLDB -.- |"存储：用户信息、\nToken记录、API-Key配置"| SQLDB
    end

    subgraph 后端异步流与 AI 生态 (AI & Data Pipeline)
        %% 分发机制
        DocRC -- "触发后台任务\n(BackgroundTasks)" --> IngestionWorker
        ChatRC -- "发起询问问答" --> RAGWorker
        
        %% 具体工作处理层
        IngestionWorker[文档解析与注入流水线]
        RAGWorker[检索及基于提示词的生成通道]
        
        %% AI 模型支撑层
        EmbeddingModel((Embedding 模型 \n 智谱/OpenAI))
        LLMModel((大规模语言模型 \n ChatGLM/千问/GPT-4))
        
        %% 数据落盘存储群
        VectorDB[(向量数据库\nMilvus/Chroma)]
        KVStore[(文档KV存储\nRedis/MongoDB)]
        
        %% 具体连接交互
        IngestionWorker <--> |"获取稠密向量"| EmbeddingModel
        RAGWorker <--> |"获取 Query 向量"| EmbeddingModel
        
        IngestionWorker --> |"1. 插入分块片段向量"| VectorDB
        IngestionWorker --> |"2. 存入母文档原文"| KVStore
        
        RAGWorker --> |"召回对比"| VectorDB
        RAGWorker --> |"溯源检索映射"| KVStore
        
        RAGWorker <--> |"传递完整语义组装生成"| LLMModel
    end

    %% 图表样式增强
    classDef client fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef sys fill:#e1f5fe,stroke:#03a9f4,stroke-width:2px;
    classDef db fill:#fff3e0,stroke:#ff9800,stroke-width:2px;
    classDef ai fill:#f3e5f5,stroke:#9c27b0,stroke-width:2px;
    
    class ClientA,ClientB client;
    class FastAPI sys;
    class SQLDB,VectorDB,KVStore db;
    class EmbeddingModel,LLMModel ai;
```

---

## 2. 深入 RAG 与多表示索引数据流图 (RAG Data Flow)

此图重点剖析在上述文字说明中提到的 **“嵌入(Embedding)”** 与 **“多表示索引(Multi-representation Indexing)”** 具体是如何处理文件的。

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户/调用者
    participant API as FastAPI 业务网关
    participant Worker as LangChain 数据拆分工厂
    participant KV as KV 母文档存储库
    participant Embed as Embedding 嵌入引擎
    participant VDB as 高维向量数据库
    participant LLM as 大型语言生成模型

    %% 注入过程
    note over User, VDB: 阶段 1: 多表示索引的数据入库过程 (Data Ingestion)
    User->>API: 上传源文件(PDF/Excel/Word)
    API->>API: 生产 doc_id，通过鉴权
    API->>Worker: 推送源文件给后台异步处理
    API-->>User: Http 201 (Status: Processing)
    
    Worker->>Worker: 提取整个章节为 [母文档 Parent Doc]
    Worker->>KV: 存入 KV 存储表 (key=doc_id, val=母文档内容)
    
    Worker->>Worker: 使用 LLM/拆分器进行“多表示提取”
    note right of Worker: 分离出:<br/>1. 全文总结 (Summary)<br/>2. 短精准切片 (Child Chunks)
    
    Worker->>Embed: 将“结论”和“短特征片”传送进行嵌入转化
    Embed-->>Worker: 返回 1536 维的数值数组 (Vectors)
    Worker->>VDB: 存入向量组，附加 metadata: {parent_id: doc_id}

    %% 问答过程
    note over User, LLM: 阶段 2: 检索与问答增强过程 (Retrieval Augmented Generation)
    User->>API: 提问 Query ("这份文档风险点在哪？")
    API->>Embed: 嵌入模型实时转化 Query 向量
    Embed-->>API: 返回 Query Vector
    
    API->>VDB: 查询离 Query 向量最近的 Top-K 特征
    VDB-->>API: 命中某“短特征块”，返回关联的 parent_id(doc_id)
    
    API->>KV: ⭐根据关联的 parent_id 提取完整的宏大母体上下文⭐
    KV-->>API: 返回一整段具备完整语境的宏大段落
    
    API->>API: 拼接 Prompt: [System Rule] + [提取出的充足上下文] + [用户Query]
    API->>LLM: 递交合成完毕的 Prompt
    LLM-->>API: 流式响应推算出的高质量答案
    API-->>User: 返回推流数据/结果 JSON
```
