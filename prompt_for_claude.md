# 给 Claude 的启动指令 (Prompt for Claude)

如果你打算将这个项目转交给正在运行的 Claude (作为研发 Agent) 来进行核心代码编写，请直接将以下这段 **Prompt** 复制并发送给它，它会自动理解重点并开始干活。

---

> **请复制以下内容发送给 Claude：**

你好，Claude。我正在开发一个**处理文档并进行对答问询的 RAG Bot**。

我的终极目标是打造一个强大的、能够上传源文档、智能解析内容并且对答精准的知识库处理器。关于接口暴露和加上 API KEY / Token 限制的细节我已经建好了一些基础的代码骨架（在 `main.py` 和 `core` 目录下有依赖注入）。**但这只是调用的拦截小细节，项目的真正灵魂是文档处理。**

请你阅读当前目录下的架构和时序图设计：
- `system_architecture_diagrams.md`
- `architecture_and_tech_stack.md`
- 当前 `routers/documents.py` 与 `routers/chat.py` 的占位代码。

阅读理解完毕后，**请你把 100% 的精力花在实现文档处理机器人的核心功能上**，这是我接下来的需求清单，请你一步步帮我用真实的代码写出来：

1. **写出解析管道 (Parser Pipeline)**：
   - 帮我引入读取主流文档(如 PDF, txt)的库（比如 `pdfplumber` 或 `unstructured`）。然后在 `routers/documents.py` 中写出真实的逻辑：当用户上传大段文章时，把文本抽离出来。

2. **落实向量数据库与多表示引擎基建 (RAG Engine)**：
   - 使用 Langchain 等技术，将抽取出来的的长文使用“母子文档（Parent-Child）”分块保存至向量库。帮我初始化并连接向量 DB (例如 Chroma 或者 Milvus 配置) 以及 Embeddings (采用 OpenAI 的 text-embedding 或其他开源方案)。
   
3. **完成核心对话检索流 (Chat Completions)**：
   - 在 `routers/chat.py` 中去掉目前的模拟回复，写上真实的检索闭环：收到用户的 Query -> 转向量 -> 搜索最高度关联的细小片段 -> 映射回溯提取整段的详细上下文 -> 组装 Prompt -> 交给 LLM (以流式生成高质量的结果)。

请你先阅读一下现在的脚手架和设计大纲，然后给出你打算怎么引入包（如 LangChain）并实现文档处理核心部分的代码结构，如果你准备好了，就给我一个技术实施清单并开始干活！
