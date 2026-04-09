#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
阶段1验证脚本 - MD导出模块 (Word/PDF) + 图片处理链路
自动验证: 图片提取 → 保存 → MD展示 → 导出还原
"""

import os
import sys
import json
import time
import tempfile

# 设置UTF-8编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# API配置
API_BASE = "http://localhost:8000/api/v1"

# 测试MD内容（包含图片引用）
TEST_MD_WITH_IMAGE = """# 测试文档

## 标题2

这是一个测试段落，包含**加粗**和*斜体*文本。

![测试图片](test_image.png)

### 列表测试
- 项目一
- 项目二
- 项目三

### 表格测试
| 姓名 | 年龄 | 城市 |
|------|------|------|
| 张三 | 25 | 北京 |
| 李四 | 30 | 上海 |

这是最后的段落。
"""


def print_header(text):
    print(f"\n{'='*60}")
    print(f"{text}")
    print(f"{'='*60}")


def print_result(name, status, details=""):
    icons = {"OK": "[OK]", "FAIL": "[FAIL]", "INFO": "[INFO]"}
    icon = icons.get(status, status)
    color = {"OK": "\033[92m", "FAIL": "\033[91m", "INFO": "\033[94m"}.get(status, "\033[0m")
    reset = "\033[0m"
    print(f"{color}{icon}{reset} {name}")
    if details:
        print(f"      {details}")


def api_request(method, endpoint, data=None):
    """发送API请求"""
    import urllib.request
    import urllib.error

    url = f"{API_BASE}{endpoint}"
    headers = {"Content-Type": "application/json"}

    try:
        if method == "GET":
            req = urllib.request.Request(url, headers=headers)
        else:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode('utf-8'),
                headers=headers,
                method=method
            )

        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8')}"}
    except Exception as e:
        return {"error": str(e)}


def check_service_health():
    """检查服务健康状态"""
    print_header("检查服务状态")
    import urllib.request
    url = "http://localhost:8000/health"
    try:
        req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            if result and result.get("status") == "ok":
                print_result("服务健康检查", "OK", f"Service: {result.get('service')}")
                return True
            else:
                print_result("服务健康检查", "FAIL", f"服务未正常运行: {result}")
                return False
    except Exception as e:
        print_result("服务健康检查", "FAIL", f"连接失败: {e}")
        return False


def test_export_formats():
    """测试导出格式列表"""
    print_header("测试导出格式列表API")
    result = api_request("GET", "/export/formats")

    if "formats" in result:
        formats = [f["id"] for f in result["formats"]]
        expected = ["docx", "pdf", "html", "txt"]
        if all(f in formats for f in expected):
            print_result("导出格式列表", "OK", f"支持格式: {', '.join(formats)}")
            return True
        else:
            print_result("导出格式列表", "FAIL", f"缺少某些格式，当前: {formats}")
            return False
    else:
        print_result("导出格式列表", "FAIL", result.get("error", "未知错误"))
        return False


def find_test_document():
    """查找测试文档"""
    storage_dir = "./storage_md"
    if os.path.exists(storage_dir):
        files = [f for f in os.listdir(storage_dir) if f.endswith(".md")]
        if files:
            for f in files:
                filepath = os.path.join(storage_dir, f)
                if os.path.getsize(filepath) > 50:
                    return f[:-3]
    return None


def test_image_extraction():
    """测试图片处理模块导入"""
    print_header("测试图片处理模块")
    try:
        from core.image_handler import (
            ImageHandler,
            extract_images_from_pdf,
            extract_images_from_docx,
            save_image_records,
            get_image_records,
            IMAGE_STORAGE_DIR
        )
        print_result("图片处理模块导入", "OK", "所有模块导入成功")
        print_result("图片存储目录", "INFO", IMAGE_STORAGE_DIR)
        return True
    except ImportError as e:
        print_result("图片处理模块导入", "FAIL", str(e))
        return False


def test_image_save_and_markdown():
    """测试图片保存和Markdown引用生成"""
    print_header("测试图片保存和Markdown引用")

    try:
        from core.image_handler import ImageHandler, IMAGE_STORAGE_DIR
        import os

        # 确保目录存在
        os.makedirs(IMAGE_STORAGE_DIR, exist_ok=True)

        # 创建一个测试图片（简单的红色方块）
        from PIL import Image
        import io

        img = Image.new('RGB', (100, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_data = img_bytes.getvalue()

        # 测试保存图片
        handler = ImageHandler("test_doc_123")
        image_info = handler.save_image(img_data, "test_red_block.png", "png")

        print_result("图片保存", "OK", f"文件: {image_info.stored_path}")

        # 测试Markdown引用生成
        md_ref = handler.get_markdown_ref(image_info, "测试图片")
        print_result("Markdown引用生成", "OK", md_ref)

        # 验证文件确实存在
        if os.path.exists(image_info.stored_path):
            print_result("图片文件存在", "OK", f"大小: {os.path.getsize(image_info.stored_path)} bytes")
        else:
            print_result("图片文件存在", "FAIL", "文件不存在")
            return False

        return True

    except Exception as e:
        print_result("图片保存测试", "FAIL", str(e))
        import traceback
        traceback.print_exc()
        return False


def test_export_with_image():
    """测试带图片的MD导出"""
    print_header("测试带图片的MD导出")

    # 创建测试图片
    try:
        from PIL import Image
        import io
        import os

        # 确保图片存储目录存在
        IMAGE_STORAGE_DIR = "./storage_images"
        os.makedirs(IMAGE_STORAGE_DIR, exist_ok=True)

        # 创建一个测试图片并保存
        img = Image.new('RGB', (200, 100), color='blue')
        img_path = os.path.join(IMAGE_STORAGE_DIR, "test_export_image.png")
        img.save(img_path)
        print_result("创建测试图片", "OK", f"路径: {img_path}")

        # 构建包含图片引用的MD内容
        md_content = f"""# 测试文档

这是一个带图片的测试文档。

![测试图片]({img_path})

这是文档内容。
"""

        # 测试导出为 DOCX
        from core.export_engine import export_md
        result = export_md("test_image_export", md_content, "docx")
        if result.get("success"):
            print_result("DOCX导出(带图片)", "OK", f"文件: {result.get('filename')}, 大小: {result.get('size')} bytes")
        else:
            print_result("DOCX导出(带图片)", "FAIL", result.get("error", "导出失败"))
            return False

        # 测试导出为 PDF
        result = export_md("test_image_export", md_content, "pdf")
        if result.get("success"):
            print_result("PDF导出(带图片)", "OK", f"文件: {result.get('filename')}, 大小: {result.get('size')} bytes")
        else:
            print_result("PDF导出(带图片)", "FAIL", result.get("error", "导出失败"))
            return False

        return True

    except Exception as e:
        print_result("图片导出测试", "FAIL", str(e))
        import traceback
        traceback.print_exc()
        return False


def test_image_reference_in_markdown():
    """测试Markdown中的图片引用解析"""
    print_header("测试Markdown图片引用解析")

    try:
        from core.export_engine import MarkdownExporter
        import os

        # 创建一个真实测试图片
        from PIL import Image
        img_path = "./storage_images/test_md_parse.png"
        os.makedirs("./storage_images", exist_ok=True)
        img = Image.new('RGB', (100, 100), color='green')
        img.save(img_path)

        md_content = f"""# Test

![Image 1]({img_path})

![Image 2]({img_path})

Some text with **bold**.
"""

        exporter = MarkdownExporter()
        images = exporter._extract_images_from_markdown(md_content)

        if len(images) == 2:
            print_result("图片引用解析", "OK", f"解析到 {len(images)} 个图片引用")
            for i, img in enumerate(images):
                print(f"      [{i+1}] {img['original_ref']}")
            return True
        else:
            print_result("图片引用解析", "FAIL", f"期望2个图片，实际{len(images)}个")
            return False

    except Exception as e:
        print_result("图片引用解析", "FAIL", str(e))
        import traceback
        traceback.print_exc()
        return False


def test_export_docx(doc_id):
    """测试导出为Word"""
    print_header(f"测试导出 Word (.docx) - doc_id: {doc_id}")
    result = api_request("POST", "/export/convert", {"doc_id": doc_id, "format": "docx"})

    if result.get("success"):
        filepath = result.get("filepath", "").replace("\\", "/")
        size = result.get("size", 0)
        images_embedded = result.get("images_embedded", 0)
        print_result("Word 导出", "OK", f"文件: {filepath}, 大小: {size} bytes")
        return True
    else:
        print_result("Word 导出", "FAIL", result.get("error", "导出失败"))
        return False


def test_export_pdf(doc_id):
    """测试导出为PDF"""
    print_header(f"测试导出 PDF (.pdf) - doc_id: {doc_id}")
    result = api_request("POST", "/export/convert", {"doc_id": doc_id, "format": "pdf"})

    if result.get("success"):
        filepath = result.get("filepath", "").replace("\\", "/")
        size = result.get("size", 0)
        print_result("PDF 导出", "OK", f"文件: {filepath}, 大小: {size} bytes")
        return True
    else:
        print_result("PDF 导出", "FAIL", result.get("error", "导出失败"))
        return False


def test_export_html(doc_id):
    """测试导出为HTML"""
    print_header(f"测试导出 HTML (.html) - doc_id: {doc_id}")
    result = api_request("POST", "/export/convert", {"doc_id": doc_id, "format": "html"})

    if result.get("success"):
        filepath = result.get("filepath", "").replace("\\", "/")
        size = result.get("size", 0)
        print_result("HTML 导出", "OK", f"文件: {filepath}, 大小: {size} bytes")
        return True
    else:
        print_result("HTML 导出", "FAIL", result.get("error", "导出失败"))
        return False


def test_export_txt(doc_id):
    """测试导出为纯文本"""
    print_header(f"测试导出 TXT (.txt) - doc_id: {doc_id}")
    result = api_request("POST", "/export/convert", {"doc_id": doc_id, "format": "txt"})

    if result.get("success"):
        filepath = result.get("filepath", "").replace("\\", "/")
        size = result.get("size", 0)
        print_result("TXT 导出", "OK", f"文件: {filepath}, 大小: {size} bytes")
        return True
    else:
        print_result("TXT 导出", "FAIL", result.get("error", "导出失败"))
        return False


def test_existing_features():
    """测试原有功能是否正常"""
    print_header("测试原有功能兼容性")

    # 测试文档列表API
    result = api_request("GET", "/documents/04cc5095-e303-4274-a596-a8a7799ef54e/status")
    if "status" in result:
        print_result("文档状态API", "OK", f"状态: {result.get('status')}")
    else:
        print_result("文档状态API", "FAIL", result.get("error", "获取失败"))

    # 测试RAG API
    doc_bot_result = api_request("GET", "/doc-bot/representations/04cc5095-e303-4274-a596-a8a7799ef54e")
    if "representations" in doc_bot_result or "detail" in doc_bot_result:
        print_result("RAG API", "OK", "API响应正常")
    else:
        print_result("RAG API", "FAIL", "API无响应")

    # 测试健康检查
    import urllib.request
    try:
        req = urllib.request.Request("http://localhost:8000/health", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as response:
            health = json.loads(response.read().decode('utf-8'))
            if health.get("status") == "ok":
                print_result("系统健康检查", "OK")
            else:
                print_result("系统健康检查", "FAIL")
    except:
        print_result("系统健康检查", "FAIL")


def main():
    print_header("阶段1验证 - MD导出模块 + 图片处理链路")

    results = []

    # 1. 检查服务状态
    results.append(("服务健康", check_service_health()))

    # 2. 测试导出格式列表
    results.append(("导出格式列表", test_export_formats()))

    # 3. 测试图片处理模块导入
    results.append(("图片处理模块", test_image_extraction()))

    # 4. 测试图片保存和Markdown引用
    results.append(("图片保存和MD引用", test_image_save_and_markdown()))

    # 5. 测试Markdown图片引用解析
    results.append(("MD图片引用解析", test_image_reference_in_markdown()))

    # 6. 测试带图片的导出
    results.append(("带图片的导出", test_export_with_image()))

    # 7. 查找测试文档
    doc_id = find_test_document()
    if not doc_id:
        print_result("查找测试文档", "FAIL", "storage_md 目录中没有找到有效的MD文件")
        doc_id = "04cc5095-e303-4274-a596-a8a7799ef54e"
        print(f"使用默认文档ID: {doc_id}")
    else:
        print_result("查找测试文档", "OK", f"使用文档: {doc_id}")

    # 8. 测试各种导出格式
    results.append(("Word 导出", test_export_docx(doc_id)))
    results.append(("PDF 导出", test_export_pdf(doc_id)))
    results.append(("HTML 导出", test_export_html(doc_id)))
    results.append(("TXT 导出", test_export_txt(doc_id)))

    # 9. 测试原有功能
    test_existing_features()

    # 汇总
    print_header("验证结果汇总")
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"\n通过: {passed}/{total}")

    for name, result in results:
        status = "OK" if result else "FAIL"
        print(f"  {status} - {name}")

    if passed == total:
        print("\n\033[92m所有验证通过！导出模块和图片处理链路工作正常。\033[0m")
        return 0
    else:
        print(f"\n\033[91m有 {total - passed} 项验证失败，请检查。\033[0m")
        return 1


if __name__ == "__main__":
    sys.exit(main())
