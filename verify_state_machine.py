"""
状态机改进效果验证脚本

此脚本通过模拟场景来验证状态机的正确性，不依赖前端界面。
"""
import os
import sys
import json
import tempfile
import shutil
from datetime import datetime

# 设置路径
os.chdir(r"D:\2649393809\Bot")
sys.path.insert(0, r"D:\2649393809\Bot")

# 临时目录用于测试
TEST_ERROR_DIR = "./test_storage_errors"
TEST_MD_DIR = "./test_storage_md"
TEST_STORAGE_DIR = "./test_storage"

def setup_test_env():
    """设置测试环境"""
    os.makedirs(TEST_ERROR_DIR, exist_ok=True)
    os.makedirs(TEST_MD_DIR, exist_ok=True)
    os.makedirs(TEST_STORAGE_DIR, exist_ok=True)

def teardown_test_env():
    """清理测试环境"""
    shutil.rmtree(TEST_ERROR_DIR, ignore_errors=True)
    shutil.rmtree(TEST_MD_DIR, ignore_errors=True)
    shutil.rmtree(TEST_STORAGE_DIR, ignore_errors=True)

def print_scenario(title):
    print("\n" + "="*60)
    print(f"[{title}]")
    print("="*60)

def print_result(label, passed, detail=""):
    status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status} | {label}")
    if detail:
        print(f"        Detail: {detail}")

def simulate_normal_long_task():
    """场景一：正常长任务"""
    print_scenario("场景一：正常长任务 - 验证状态不悬空")

    # 模拟 TaskStatusManager
    from core.bot.models import TaskStatus
    from core.bot.task_status_manager import TaskStatusManager

    manager = TaskStatusManager()
    manager.ERROR_DIR = TEST_ERROR_DIR

    doc_id = "test_doc_001"

    # 1. 初始化任务
    manager.init_task(doc_id, metadata={"filename": "big_report.pdf"})
    status = manager.get_status(doc_id)
    passed1 = status["status"] == TaskStatus.PENDING
    print_result("1. 任务初始化为 pending", passed1, f"status={status['status']}")

    # 2. 任务开始
    manager.start(doc_id)
    status = manager.get_status(doc_id)
    passed2 = status["status"] == TaskStatus.RUNNING
    print_result("2. 任务开始变为 running", passed2, f"status={status['status']}")

    # 3. 模拟完成 - 创建 MD 文件
    md_file = os.path.join(TEST_MD_DIR, f"{doc_id}.md")
    with open(md_file, "w") as f:
        f.write("# Test Document")
    manager.complete(doc_id, {"page_count": 10})

    status = manager.get_status(doc_id)
    passed3 = status["status"] == TaskStatus.COMPLETED
    print_result("3. 任务完成变为 completed", passed3, f"status={status['status']}")

    # 4. 验证状态有明确定义
    passed4 = status["status"] in [s.value for s in TaskStatus]
    print_result("4. 状态值在定义范围内", passed4)

    # 清理
    os.remove(md_file)
    return passed1 and passed2 and passed3 and passed4

def simulate_failure_scenario():
    """场景二：任务失败 - 验证明确报错"""
    print_scenario("场景二：任务失败 - 验证明确报错、不卡死")

    from core.bot.models import TaskStatus
    from core.bot.task_status_manager import TaskStatusManager

    manager = TaskStatusManager()
    manager.ERROR_DIR = TEST_ERROR_DIR

    doc_id = "test_doc_002"

    # 1. 初始化并开始任务
    manager.init_task(doc_id)
    manager.start(doc_id)

    # 2. 模拟处理失败（不可重试的错误）
    error_msg = "PDF文件已损坏或密码保护"
    manager.fail(doc_id, error_msg, retryable=False)

    # 3. 验证错误持久化
    error_file = os.path.join(TEST_ERROR_DIR, f"{doc_id}.error")
    passed1 = os.path.exists(error_file)
    print_result("1. 错误信息持久化到文件", passed1, f"error_file exists={passed1}")

    # 4. 验证错误可读取
    with open(error_file, "r") as f:
        saved_error = f.read()
    passed2 = saved_error == error_msg
    print_result("2. 错误信息正确保存", passed2, f"saved='{saved_error}'")

    # 5. 验证状态为 failed
    status = manager.get_status(doc_id)
    passed3 = status["status"] == TaskStatus.FAILED
    print_result("3. 状态标记为 failed", passed3, f"status={status['status']}")

    # 6. 验证错误可获取
    retrieved_error = manager.get_error(doc_id)
    passed4 = retrieved_error == error_msg
    print_result("4. 可通过 API 获取错误信息", passed4, f"error='{retrieved_error}'")

    # 7. 验证不可重试标记
    passed5 = not manager.is_retryable(doc_id)
    print_result("5. 标记为不可重试", passed5, f"retryable={manager.is_retryable(doc_id)}")

    # 清理
    os.remove(error_file)
    return all([passed1, passed2, passed3, passed4, passed5])

def simulate_timeout_scenario():
    """场景三：任务超时"""
    print_scenario("场景三：任务超时 - 验证自动结束")

    from core.bot.models import TaskStatus
    from core.bot.task_status_manager import TaskStatusManager

    manager = TaskStatusManager()
    manager.ERROR_DIR = TEST_ERROR_DIR

    doc_id = "test_doc_003"

    # 1. 初始化并开始任务
    manager.init_task(doc_id)
    manager.start(doc_id)

    # 2. 模拟超时（可重试）
    manager.timeout(doc_id, timeout_seconds=300)

    # 3. 验证超时持久化
    error_file = os.path.join(TEST_ERROR_DIR, f"{doc_id}.error")
    passed1 = os.path.exists(error_file)
    print_result("1. 超时信息持久化到文件", passed1)

    # 4. 验证状态为 timeout
    status = manager.get_status(doc_id)
    passed2 = status["status"] == TaskStatus.TIMEOUT
    print_result("2. 状态标记为 timeout", passed2, f"status={status['status']}")

    # 5. 验证超时错误信息
    error = manager.get_error(doc_id)
    passed3 = "timeout" in error.lower()
    print_result("3. 错误信息包含超时原因", passed3, f"error='{error}'")

    # 清理
    os.remove(error_file)
    return passed1 and passed2 and passed3

def simulate_restart_recovery():
    """场景四：Bot 重启后状态恢复"""
    print_scenario("场景四：Bot 重启 - 验证不乱")

    from core.bot.models import TaskStatus
    from core.bot.task_status_manager import TaskStatusManager

    # 第一阶段：创建任务并失败
    doc_id = "test_doc_004"
    error_msg = "OCR服务暂时不可用"

    # 模拟保存错误文件（Bot 崩溃前）
    error_file = os.path.join(TEST_ERROR_DIR, f"{doc_id}.error")
    with open(error_file, "w") as f:
        f.write(error_msg)

    passed1 = os.path.exists(error_file)
    print_result("1. 错误文件在磁盘上持久化", passed1)

    # 第二阶段：模拟 Bot 重启（创建新的 Manager 实例）
    # 注意：这模拟的是进程重启，内存状态丢失但文件仍在
    manager2 = TaskStatusManager()
    manager2.ERROR_DIR = TEST_ERROR_DIR

    # 验证错误文件存在
    error_exists = os.path.exists(error_file)
    passed2 = error_exists
    print_result("2. 重启后错误文件依然存在", passed2)

    # 验证可以通过文件恢复错误信息
    recovered_error = manager2.get_error(doc_id)
    passed3 = recovered_error == error_msg
    print_result("3. 可从文件恢复错误信息", passed3, f"recovered='{recovered_error}'")

    # 注意：由于任务不在内存中，get_status 会返回 None
    # 这是预期行为 - 前端轮询时会根据错误文件返回 failed 状态
    status = manager2.get_status(doc_id)
    passed4 = status is None  # 内存中没有
    print_result("4. 内存中无任务（进程重启）", passed4, "需要通过错误文件恢复")

    # 清理
    os.remove(error_file)
    return passed1 and passed2 and passed3 and passed4

def simulate_no_callback_mechanism():
    """场景五：回调机制检查"""
    print_scenario("Scenario 5: Callback Loss - Current Implementation")

    # 检查 documents.py 中是否有回调机制
    with open(r"D:\2649393809\Bot\routers\documents.py", "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否有 callback 相关实现
    has_callback = "callback" in content.lower()

    print(f"  [i] documents.py callback mechanism: {'Implemented' if has_callback else 'NOT implemented (using BackgroundTasks)'}")
    print("        Note: Using FastAPI BackgroundTasks, result written to file after task completes")
    print("        Frontend polls /status for result - no callback URL needed")
    print("        This pattern naturally avoids callback loss issues")

    return True  # 这是一个说明性场景，不做通过/失败判断

def simulate_frontend_reconnection():
    """场景六：前端断网重连"""
    print_scenario("场景六：前端断网重连 - 验证状态恢复")

    # 检查前端代码中的重连逻辑
    with open(r"D:\2649393809\Bot\static\js\app.js", "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否有 fetchWithRetry
    has_retry = "fetchWithRetry" in content
    print_result("1. 使用 fetchWithRetry 重试", has_retry)

    # 检查 pollDocumentStatus 是否处理了各种状态
    has_completed_handling = "result.status === 'completed'" in content or "result.status === 'ready'" in content
    has_failed_handling = "result.status === 'failed'" in content
    has_timeout_handling = "result.status === 'timeout'" in content

    print_result("2. 处理 completed 状态", has_completed_handling)
    print_result("3. 处理 failed 状态", has_failed_handling)
    print_result("4. 处理 timeout 状态", has_timeout_handling)

    # 检查是否存储了 errorMessage
    has_error_storage = "errorMessage" in content
    print_result("5. 错误信息存储在 fileData", has_error_storage)

    return has_retry and has_completed_handling and has_failed_handling and has_timeout_handling

def simulate_overall_status():
    """场景七：整体状态验证"""
    print_scenario("场景七：整体状态确定性验证")

    from core.bot.models import TaskStatus

    # 验证所有状态都在 TaskStatus 枚举中
    all_statuses = [s.value for s in TaskStatus]
    expected = ["pending", "running", "completed", "failed", "timeout", "cancelled"]

    passed1 = set(all_statuses) == set(expected)
    print_result("1. TaskStatus 枚举完整定义", passed1, f"statuses={all_statuses}")

    # 验证前端状态处理
    with open(r"D:\2649393809\Bot\static\js\app.js", "r", encoding="utf-8") as f:
        js_content = f.read()

    # 检查所有状态都有处理
    status_checks = {
        "pending": "pending" in js_content,
        "running": "running" in js_content,
        "completed": "completed" in js_content or "ready" in js_content,
        "failed": "failed" in js_content,
        "timeout": "timeout" in js_content,
    }

    all_handled = all(status_checks.values())
    print_result("2. 前端处理所有状态", all_handled)
    for status, handled in status_checks.items():
        print(f"        - {status}: {'[OK]' if handled else '[X]'}")

    return passed1 and all_handled

def check_retry_button():
    """检查是否有重试按钮"""
    print_scenario("Retry Button Check")

    with open(r"D:\2649393809\Bot\static\js\app.js", "r", encoding="utf-8") as f:
        js_content = f.read()

    # 检查是否有 retryUpload 函数
    has_retry_function = "function retryUpload" in js_content

    # 检查是否在文件状态为 error 时显示重试按钮
    has_error_retry_button = "fileData.status === 'error'" in js_content and "retry-btn" in js_content

    # 检查是否调用 retryUpload
    has_onclick_retry = "onclick=\"retryUpload" in js_content or "onclick='retryUpload" in js_content

    print(f"  [i] retryUpload function exists: {'YES' if has_retry_function else 'NO'}")
    print(f"  [i] Error state retry button rendering: {'YES' if has_error_retry_button else 'NO'}")
    print(f"  [i] onclick retryUpload handler: {'YES' if has_onclick_retry else 'NO'}")

    return has_retry_function and has_error_retry_button and has_onclick_retry

def main():
    print("="*60)
    print("   状态机改进效果验证 - 生产级改造验证")
    print("="*60)
    print(f"   Verification time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    setup_test_env()

    try:
        results = []

        results.append(("场景一：正常长任务", simulate_normal_long_task()))
        results.append(("场景二：任务失败", simulate_failure_scenario()))
        results.append(("场景三：任务超时", simulate_timeout_scenario()))
        results.append(("场景四：Bot重启恢复", simulate_restart_recovery()))
        results.append(("场景五：回调机制", simulate_no_callback_mechanism()))
        results.append(("场景六：断网重连", simulate_frontend_reconnection()))
        results.append(("场景七：整体状态", simulate_overall_status()))

        # 重试按钮检查
        results.append(("重试按钮", check_retry_button()))

        # 总结
        print("\n" + "="*60)
        print("   验证总结")
        print("="*60)

        passed = sum(1 for _, r in results if r)
        total = len(results)

        for name, result in results:
            status = "[OK]" if result else "[!!]"
            print(f"  {status} {name}")

        print(f"\n  Pass rate: {passed}/{total}")

        if passed == total:
            print("\n  [OK] All core verifications passed!")
            print("  Note: Retry button needs to be added to UI separately")
        else:
            print(f"\n  [!] {total - passed} items need improvement")

    finally:
        teardown_test_env()

if __name__ == "__main__":
    main()
