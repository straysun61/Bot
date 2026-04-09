# 任务：修复 RAG 模块中缺失的向量切分与入库分离逻辑

## 背景
我们在之前重构 `core/rag_engine.py` 里的 `DocumentParser` 时，为 `process_document()` 函数加入了高级的 OCR 和 Markdown 格式复原功能。但是，这个函数在重构后，**遗漏了针对生成的 Markdown 文本进行大语言模型所必须的切割（Text Split）和向量库（ChromaDB）与文档库（docstore）的入库逻辑**。目前的 RAG 引擎形同虚设。

## 修复目标
请你修改 `core/rag_engine.py` 文件中的 `process_document` 方法，将其补充为一个**真正的实现了多表示索引 (Multi-vector Retriever / Parent-Child)** 的完整管道。

### 具体的实现要求：

1. **保留目前的极佳特性**：保留在函数前段关于 `markdown_text, page_mappings = DocumentParser.parse_file(...)` 以及处理图片的整个完整逻辑。

2. **在 `return` 语句之前，引入切块器（Splitters）**：
   - 引入母文档切分器 `parent_splitter`，基于 `RecursiveCharacterTextSplitter`，`chunk_size` 设为 `2000`，`chunk_overlap` 设为 `100`。
   - 引入子文档（检索用）切分器 `child_splitter`，`chunk_size` 设为 `400`，`chunk_overlap` 设为 `50`。

3. **执行切分操作**：
   - 使用 `parent_splitter.create_documents([markdown_text])` 把刚才解析出的 markdown 文本切成大块。
   - 必须通过循环，为每一个大块赋予一个全局唯一的 `parent_id`（例如 uuid）。并将这个 `parent_id` 连同传入的 `doc_id` 写进该大块文档的 `metadata` 中。

4. **进行母子映射与入库**：
   - 遍历生成的所有大块（母文档），使用 `child_splitter` 将这个母文档的文本再次切分为多个小块（子文档）。
   - **至关重要**：必须将母块分配到的那个 `parent_id` 以及原始的 `doc_id` 信息，同时存入所有这些对应的新切出来的子文档的 `metadata` 中。
   - 将所有切出来的短小**子文档**，添加到 Chroma 向量数据库：`self.vectorstore.add_documents(child_docs)`
   - 将所有具有完整上下文的大段**母文档**，以 KV 对 `(parent_id, Document)` 的形式，添加到本地内存文档库中：`self.retriever.docstore.mset(list_of_tuples)`

5. **返回值不受影响**：
   - 保持最后返回原本的 `dict` 结构不变（包含 `doc_id`, `markdown`, `page_mappings` 等）。

### 自动化验证与自我验收机制：
在你完成 `core/rag_engine.py` 的代码修改后，**你必须自己编写一个测试脚本来验证你的修改是否成功！**
1. 在根目录下创建一个临时的测试脚本 `test_rag_pipeline.py`。
2. 在该脚本中实例化 `RAGEngine`。
3. 把一个简单的文本生成 Markdown 后直接通过代码喂给 `process_document`（你可以临时写死一段带标题的长文本进行模拟测试，跳过真实文件解析的 OCR 环节以加速测试）。
4. 代码执行完后，打印出当前本地的 ChromaDB 里的文档数量（如 `engine.vectorstore._collection.count()`），验证数据库里确实存入了多条被切割后的数据！
5. 在终端执行 `python test_rag_pipeline.py`。如果打印结果证明存入了向量，向我汇报。

**（用户提示：等 Claude 汇报它自己测试通过后，您也可以直接打开 `http://127.0.0.1:8000/docs` 的 Swagger 前端页面。按之前的步骤先 Auth 拿到 Token，再去 Document 接口传一个真实的文件，看能否成功并在 Chat 接口实现精准 RAG 问答测试哦！）**
