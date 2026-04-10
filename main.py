"""
机器人统一架构 - FastAPI应用入口
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.bot import (
    get_config,
    get_task_executor,
    get_task_queue,
    get_callback_handler,
    get_conversation_manager,
    webhook_router,
    set_task_handler,
)
from routers import auth, documents, chat, doc_bot, bot_router, export


async def handle_task(task):
    """任务处理回调"""
    executor = get_task_executor()
    await executor.submit_task(task)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    import os

    # Startup
    config = get_config()

    # 设置任务处理器
    set_task_handler(handle_task)

    # 仅在非 Vercel 环境启动后台服务
    if os.getenv("VERCEL") is None:
        # 启动任务执行器
        executor = get_task_executor()
        await executor.start()
        executor.start_workers(num_workers=2)

        # 启动任务队列
        queue = get_task_queue()

        # 启动对话管理器
        conv_mgr = get_conversation_manager()
        await conv_mgr.start()

        yield

        # Shutdown
        await executor.stop()
        await conv_mgr.stop()
    else:
        # Vercel Serverless 环境
        yield


app = FastAPI(
    title="Robot Unified Architecture API",
    description="统一机器人架构，支持SSE/Webhook任务接收、多等级算力调度、多轮对话",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(doc_bot.router, tags=["DocBot"])
app.include_router(bot_router.router, tags=["Bot"])
app.include_router(export.router, tags=["Export"])
app.include_router(webhook_router)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "robot-unified",
        "features": ["multi-tier-compute", "sse-webhook", "multi-turn-dialogue", "retry-timeout"]
    }


@app.get("/")
async def root():
    """前端页面"""
    from fastapi.responses import FileResponse, RedirectResponse
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    static_index = os.path.join(base_dir, "static", "index.html")
    if os.path.exists(static_index):
        return FileResponse(static_index)
    return RedirectResponse(url="/docs")


# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")
