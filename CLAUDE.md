# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Document Processing RAG (Retrieval Augmented Generation) Bot** built with FastAPI in Python. The system accepts document uploads, processes them using multi-representation indexing (Parent-Child strategy), stores vectors in ChromaDB/Milvus, and provides chat-based Q&A against the document corpus.

Key capabilities:
- Multi-tier compute power allocation (free/low/high/ultra tiers via different API providers)
- SSE/Webhook task receiving for async job processing
- Multi-turn conversation context management
- Document parsing (PDF, txt) with OCR support
- Streaming and non-streaming LLM responses

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py

# Or with uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Architecture

```
main.py                    # FastAPI app entry, lifespan management, route registration
├── core/
│   ├── bot/               # Bot infrastructure: task execution, conversation management,
│   │   │                   # retry logic, SSE client, webhook server, tier management
│   │   ├── task_executor.py
│   │   ├── conversation.py
│   │   ├── retry.py
│   │   ├── sse_client.py
│   │   ├── webhook_server.py
│   │   └── tier_manager.py
│   ├── rag_engine.py      # Core RAG engine (retrieval, multi-representation indexing)
│   ├── doc_bot.py         # Document bot core logic
│   ├── doc_bot_rag.py     # RAG with multi-turn conversation support
│   ├── export_engine.py   # Export documents to various formats
│   └── image_handler.py   # Image processing / OCR
├── routers/
│   ├── auth.py            # JWT / API-Key authentication
│   ├── documents.py       # Document upload & management endpoints
│   ├── chat.py            # /chat/completions RAG endpoint (core RAG flow)
│   ├── doc_bot.py         # DocBot-specific endpoints
│   ├── bot_router.py      # General bot routes
│   └── export.py          # Document export endpoints
└── static/, templates/    # Static files and templates
```

### RAG Data Flow

1. **Ingestion**: Upload PDF → LangChain splits into Parent/Child chunks → Embedding model → VectorDB (Chroma/Milvus) + KV store for raw content
2. **Query**: User question → Embed query vector → VectorDB similarity search → Map to parent document via doc_id → Build prompt with full context → LLM generates answer
3. **Multi-turn**: ConversationManager maintains chat history per (doc_id, session_id)

### Multi-Tier Compute

The system routes LLM requests across 4 tiers (FREE/LOW/HIGH/ULTRA) based on user tier, configured in `.env`. Each tier specifies: `_KEY`, `_TYPE` (openai-compatible/anthropic-compatible), `_BASE` (API base URL), `_MODEL`.

## Key Configuration (.env)

```bash
OPENAI_API_KEY=           # Primary LLM API key
OPENAI_API_BASE=          # API base URL (e.g., https://api.openai.com/v1)
LLM_MODEL=                # Model name

# Task processing
TASK_RECEIVER_MODE=       # sse or webhook
TASK_TIMEOUT_SECONDS=600
PER_HOUR_TASK_LIMIT=100
```

## Important Implementation Notes

- The RAG core retrieval logic is in `routers/chat.py` (`chat_completion`) which calls `rag_engine.retrieve_with_expansion()` for multi-representation retrieval
- `core/doc_bot_rag.py` provides the higher-level `DocBotRAG` class combining RAG + multi-turn conversation context
- Document parsing uses `pdfplumber` and `PyMuPDF`; OCR uses `Pillow` + vision models
- Task execution uses async workers (`task_executor.py`) with retry (`retry.py`) and timeout (`async_timeout`) decorators
- SSE and Webhook modes are supported for receiving tasks from external schedulers
