// API 配置
const API_BASE = '/api/v1';
const DOC_BOT_API = '/api/v1/doc-bot';

// 自动处理开关
let autoAIProcessing = false;

// 工具函数：格式化文件大小
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// 工具函数：获取文件图标SVG
function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const icons = {
        'pdf': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="15" x2="15" y2="15"/></svg>`,
        'doc': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,
        'docx': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,
        'xlsx': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="8" y2="17"/><line x1="12" y1="13" x2="12" y2="17"/><line x1="16" y1="13" x2="16" y2="17"/></svg>`,
        'xls': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="8" y2="17"/><line x1="12" y1="13" x2="12" y2="17"/><line x1="16" y1="13" x2="16" y2="17"/></svg>`,
        'txt': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,
        'md': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M10 12l-2 3h4l-2 3"/><line x1="8" y1="21" x2="16" y2="21"/></svg>`,
        'png': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`,
        'jpg': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`,
        'jpeg': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`
    };
    return icons[ext] || icons['txt'];
}

// 工具函数：显示 Toast 提示
function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = 'toast ' + type + ' show';
    setTimeout(() => {
        toast.className = 'toast';
    }, 3000);
}

// 获取文件类型标签
function getFileTypeLabel(ext) {
    const labels = {
        'pdf': 'PDF文档',
        'doc': 'Word文档',
        'docx': 'Word文档',
        'xlsx': 'Excel表格',
        'xls': 'Excel表格',
        'txt': '文本文件',
        'md': 'Markdown',
        'png': '图片',
        'jpg': '图片',
        'jpeg': '图片'
    };
    return labels[ext] || '文档';
}

// 获取文件类型处理提示
function getFileTypeHint(ext) {
    const hints = {
        'pdf': '文字识别和提取',
        'doc': '转换为可编辑文本',
        'docx': '转换为可编辑文本',
        'xlsx': '提取表格数据',
        'xls': '提取表格数据',
        'png': 'OCR文字识别',
        'jpg': 'OCR文字识别',
        'jpeg': 'OCR文字识别',
        'txt': '直接读取文本',
        'md': '解析Markdown'
    };
    return hints[ext] || '';
}

// DOM 元素
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const fileList = document.getElementById('fileList');
const progressArea = document.getElementById('progressArea');
const progressFilename = document.getElementById('progressFilename');
const progressStatus = document.getElementById('progressStatus');
const progressFill = document.getElementById('progressFill');
const historyList = document.getElementById('historyList');
const autoProcessSwitch = document.getElementById('autoProcessSwitch');

// 文件状态管理
const files = new Map();
let uploadQueue = [];
let isProcessing = false;

// AI 处理状态管理
const aiProcessedDocs = new Map(); // docId -> { status, representations, mdContent }

// 多轮对话历史存储
const qaHistoryStore = new Map(); // docId -> [{question, answer, timestamp}]

// 当前 AI 模态框中的 docId
let currentAIDocId = null;

// fetchWithRetry - 3次重试，指数退避
async function fetchWithRetry(url, options = {}, retries = 3, backoff = 1000) {
    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            // 错误分类
            if (response.status === 413) {
                throw new Error('FILE_TOO_LARGE');
            }
            throw new Error(`HTTP_${response.status}`);
        }
        return response;
    } catch (error) {
        if (retries === 0 || error.message === 'FILE_TOO_LARGE') {
            throw error;
        }
        // 网络错误或超时，等待后重试
        await new Promise(resolve => setTimeout(resolve, backoff));
        return fetchWithRetry(url, options, retries - 1, backoff * 2);
    }
}

// 拖拽上传
uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('dragover');
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    const droppedFiles = Array.from(e.dataTransfer.files);
    handleFiles(droppedFiles);
});

// 点击上传
uploadArea.addEventListener('click', () => {
    fileInput.click();
});

fileInput.addEventListener('change', (e) => {
    const selectedFiles = Array.from(e.target.files);
    handleFiles(selectedFiles);
    fileInput.value = '';
});

// 自动处理开关初始化
function initAutoProcessSwitch() {
    const saved = localStorage.getItem('autoAIProcessing');
    if (saved === 'true') {
        autoAIProcessing = true;
        autoProcessSwitch.checked = true;
    }
}

autoProcessSwitch.addEventListener('change', (e) => {
    autoAIProcessing = e.target.checked;
    localStorage.setItem('autoAIProcessing', autoAIProcessing);
});

// 处理文件
function handleFiles(newFiles) {
    const validTypes = ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.txt', '.md', '.png', '.jpg', '.jpeg'];
    const maxSize = 50 * 1024 * 1024; // 50MB

    for (const file of newFiles) {
        const ext = '.' + file.name.split('.').pop().toLowerCase();

        // 检查文件类型
        if (!validTypes.includes(ext)) {
            showToast(`不支持的文件类型: ${file.name}`, 'error');
            continue;
        }

        // 检查文件大小
        if (file.size > maxSize) {
            showToast(`文件太大: ${file.name} (最大50MB)`, 'error');
            continue;
        }

        // 重复上传检测
        for (const [fileId, fileData] of files) {
            if (fileData.name === file.name && fileData.status !== 'error') {
                showToast(`文件已在队列中: ${file.name}`, 'error');
                continue;
            }
        }

        // 生成文件ID
        const fileId = 'file_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        files.set(fileId, {
            id: fileId,
            file: file,
            name: file.name,
            size: file.size,
            status: 'pending',
            docId: null,
            errorType: null
        });

        // 添加到上传队列
        uploadQueue.push(fileId);
    }

    renderFileList();
    processQueue();
}

// 渲染文件列表
function renderFileList() {
    fileList.innerHTML = '';

    files.forEach((fileData, fileId) => {
        const ext = fileData.name.split('.').pop().toLowerCase();
        const item = document.createElement('div');
        item.className = 'file-item';
        item.dataset.fileId = fileId;

        let iconClass = 'file-icon';
        if (['pdf'].includes(ext)) iconClass += ' pdf';
        else if (['doc', 'docx'].includes(ext)) iconClass += ' doc';
        else if (['xlsx', 'xls'].includes(ext)) iconClass += ' xlsx';
        else if (['png', 'jpg', 'jpeg'].includes(ext)) iconClass += ' img';
        else iconClass += ' txt';

        // 大文件提示
        const isLargeFile = fileData.size > 10 * 1024 * 1024;
        const largeHint = isLargeFile ? '<div class="file-large-hint">大文件，可能需要较长时间</div>' : '';

        // 文件类型提示
        const typeHint = getFileTypeHint(ext);
        const hintHtml = typeHint ? `<div class="file-type-hint">${typeHint}</div>` : '';

        let actionButton = '';
        console.log('[DEBUG] renderFileList status check:', fileId, fileData.status, 'isError:', fileData.status === 'error');
        if (fileData.status === 'error') {
            // 失败状态 - 显示重试按钮
            actionButton = `
                <button class="action-btn retry-btn" onclick="retryUpload('${fileId}')">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
                    重试
                </button>
            `;
            console.log('[DEBUG] actionButton set to retry button for:', fileId);
        } else if (fileData.status === 'done' && fileData.docId) {
            const aiStatus = aiProcessedDocs.get(fileData.docId);
            const aiStatusClass = aiStatus ? (aiStatus.status === 'ready' ? 'ai-ready' : 'ai-processing') : '';
            const aiStatusText = aiStatus ? (aiStatus.status === 'ready' ? '已就绪' : '处理中...') : 'AI处理';

            actionButton = `
                <button class="action-btn ai-btn ${aiStatusClass}" onclick="handleAIAction('${fileData.docId}', '${escapeHtml(fileData.name)}')">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2a10 10 0 1 0 10 10H12V2z"/><path d="M12 2a10 10 0 0 1 10 10"/></svg>
                    ${aiStatusText}
                </button>
                <button class="action-btn view-btn" onclick="viewContent('${fileData.docId}', '${escapeHtml(fileData.name)}')">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                    查看
                </button>
                <button class="action-btn download-btn" onclick="downloadContent('${fileData.docId}', '${escapeHtml(fileData.name)}')">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    下载
                </button>
                <div class="action-btn export-btn" style="position:relative;">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    导出
                    <div class="export-dropdown" id="exportDropdown_${fileId}">
                        <button class="export-dropdown-item" onclick="handleExport('${fileData.docId}', '${escapeHtml(fileData.name)}', 'docx')">
                            <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                            Word 文档
                        </button>
                        <button class="export-dropdown-item" onclick="handleExport('${fileData.docId}', '${escapeHtml(fileData.name)}', 'pdf')">
                            <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
                            PDF 文档
                        </button>
                        <div class="export-dropdown-divider"></div>
                        <button class="export-dropdown-item" onclick="handleExport('${fileData.docId}', '${escapeHtml(fileData.name)}', 'html')">
                            <svg viewBox="0 0 24 24"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
                            HTML 网页
                        </button>
                        <button class="export-dropdown-item" onclick="handleExport('${fileData.docId}', '${escapeHtml(fileData.name)}', 'txt')">
                            <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                            纯文本
                        </button>
                    </div>
                </div>
            `;
        }

        // 统一状态显示
        let unifiedStatusText = getUnifiedStatusText(fileData);
        let unifiedStatusClass = getUnifiedStatusClass(fileData);

        item.innerHTML = `
            <div class="${iconClass}">${getFileIcon(fileData.name)}</div>
            <div class="file-info">
                <div class="file-name">${fileData.name}</div>
                ${hintHtml}
                ${largeHint}
            </div>
            ${actionButton}
            <span class="file-status ${unifiedStatusClass}">${unifiedStatusText}</span>
        `;
        fileList.appendChild(item);
    });
}

// 获取统一状态文本
function getUnifiedStatusText(fileData) {
    if (fileData.status === 'pending' || fileData.status === 'uploading') {
        return '上传中';
    }
    if (fileData.status === 'processing') {
        return '转换中';
    }
    if (fileData.status === 'done') {
        const aiStatus = aiProcessedDocs.get(fileData.docId);
        if (!aiStatus) {
            return '待AI处理';
        }
        if (aiStatus.status === 'processing') {
            return 'AI分析中';
        }
        if (aiStatus.status === 'ready') {
            return '已就绪';
        }
    }
    if (fileData.status === 'error') {
        if (fileData.errorType === 'FILE_TOO_LARGE') {
            return '文件太大';
        }
        return '失败';
    }
    return fileData.status;
}

// 获取统一状态样式
function getUnifiedStatusClass(fileData) {
    if (fileData.status === 'error') {
        return 'error';
    }
    if (fileData.status === 'done') {
        const aiStatus = aiProcessedDocs.get(fileData.docId);
        if (aiStatus && aiStatus.status === 'ready') {
            return 'done';
        }
    }
    if (fileData.status === 'processing') {
        return 'processing';
    }
    return 'pending';
}

// 重试上传
async function retryUpload(fileId) {
    const fileData = files.get(fileId);
    if (fileData) {
        fileData.status = 'pending';
        fileData.errorType = null;
        renderFileList();
        uploadQueue.push(fileId);
        processQueue();
    }
}

// AI 处理按钮动作
async function handleAIAction(docId, filename) {
    const aiStatus = aiProcessedDocs.get(docId);

    if (!aiStatus) {
        // 启动 AI 处理
        await startAIProcessing(docId, filename);
    } else if (aiStatus.status === 'ready') {
        // 打开 AI 对话框
        openAIModal(docId, filename);
    } else {
        // 处理中，显示提示
        showToast('文档正在处理中，请稍候...', 'info');
    }
}

// 启动 AI 处理
async function startAIProcessing(docId, filename) {
    try {
        // 显示处理中状态
        aiProcessedDocs.set(docId, { status: 'processing', representations: null, mdContent: null });
        renderFileList();
        showToast('正在启动 AI 处理...', 'info');

        // 显示 AI 处理进度条
        showAIProgress();

        // 获取文档内容
        updateAIProgress(0, '提取文本');
        const contentResp = await fetch(`${API_BASE}/documents/${docId}/content`);
        if (!contentResp.ok) throw new Error('获取文档内容失败');
        const contentResult = await contentResp.json();

        // 调用 AI 处理接口
        updateAIProgress(33, '生成表示');
        const processResp = await fetch(`${DOC_BOT_API}/process-v2`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                doc_id: docId,
                md_content: contentResult.content
            })
        });

        if (!processResp.ok) throw new Error('AI 处理失败');
        const processResult = await processResp.json();

        // 更新状态
        aiProcessedDocs.set(docId, {
            status: 'ready',
            representations: processResult,
            mdContent: contentResult.content
        });

        updateAIProgress(100, '处理完成');
        setTimeout(() => {
            hideAIProgress();
        }, 800);

        showToast('AI 处理完成！', 'success');
        renderFileList();

        // 自动打开 AI 对话框
        openAIModal(docId, filename);

    } catch (error) {
        console.error('AI 处理失败:', error);
        aiProcessedDocs.delete(docId);
        hideAIProgress();

        let errorMsg = 'AI 处理失败: ' + error.message;
        if (error.message === 'FILE_TOO_LARGE') {
            errorMsg = 'AI 处理失败: 文件太大';
        } else if (error.message.includes('HTTP_')) {
            errorMsg = 'AI 处理失败: 服务器错误';
        } else if (error.message.includes('network') || error.message.includes('fetch')) {
            errorMsg = 'AI 处理失败: 网络错误，请检查网络';
        }
        showToast(errorMsg, 'error');
        renderFileList();
    }
}

// 显示 AI 处理进度
function showAIProgress() {
    let progressEl = document.getElementById('aiProgressModal');
    if (!progressEl) {
        progressEl = document.createElement('div');
        progressEl.id = 'aiProgressModal';
        progressEl.className = 'modal-overlay';
        progressEl.innerHTML = `
            <div class="modal-content" style="max-width: 400px;">
                <div class="modal-header">
                    <h3>AI 处理中</h3>
                </div>
                <div class="ai-progress-stages" id="aiProgressStages">
                    <div class="ai-progress-stage" data-stage="0">
                        <div class="stage-icon" id="stageIcon0">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                        </div>
                        <div class="stage-info">
                            <div class="stage-name">提取文本</div>
                            <div class="stage-status" id="stageStatus0">等待中</div>
                        </div>
                    </div>
                    <div class="ai-progress-stage" data-stage="33">
                        <div class="stage-icon" id="stageIcon33">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M12 2a10 10 0 1 0 10 10H12V2z"/></svg>
                        </div>
                        <div class="stage-info">
                            <div class="stage-name">生成表示</div>
                            <div class="stage-status" id="stageStatus33">等待中</div>
                        </div>
                    </div>
                    <div class="ai-progress-stage" data-stage="66">
                        <div class="stage-icon" id="stageIcon66">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
                        </div>
                        <div class="stage-info">
                            <div class="stage-name">构建索引</div>
                            <div class="stage-status" id="stageStatus66">等待中</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(progressEl);
    }
    progressEl.style.display = 'flex';
}

function updateAIProgress(percent, status) {
    // 更新图标状态
    [0, 33, 66].forEach(p => {
        const iconEl = document.getElementById(`stageIcon${p}`);
        const statusEl = document.getElementById(`stageStatus${p}`);
        if (iconEl && statusEl) {
            if (percent > p) {
                iconEl.className = 'stage-icon done';
                statusEl.textContent = '完成';
            } else if (percent === p) {
                iconEl.className = 'stage-icon active';
                statusEl.textContent = status;
                statusEl.className = 'stage-status active';
            } else {
                iconEl.className = 'stage-icon';
                statusEl.textContent = '等待中';
                statusEl.className = 'stage-status';
            }
        }
    });
}

function hideAIProgress() {
    const progressEl = document.getElementById('aiProgressModal');
    if (progressEl) {
        progressEl.style.display = 'none';
    }
}

// 打开 AI 模态框
function openAIModal(docId, filename) {
    const aiStatus = aiProcessedDocs.get(docId);
    if (!aiStatus || !aiStatus.representations) {
        showToast('请先进行 AI 处理', 'error');
        return;
    }

    currentAIDocId = docId;

    // 移除已存在的模态框
    const existing = document.getElementById('aiModal');
    if (existing) existing.remove();

    // 获取已就绪的文档列表
    const readyDocs = [];
    files.forEach((fileData) => {
        if (fileData.status === 'done' && fileData.docId) {
            const status = aiProcessedDocs.get(fileData.docId);
            if (status && status.status === 'ready') {
                readyDocs.push({ docId: fileData.docId, name: fileData.name });
            }
        }
    });

    const modal = document.createElement('div');
    modal.id = 'aiModal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal-content ai-modal">
            <div class="ai-modal-header">
                <h3>${escapeHtml(filename)}</h3>
                ${readyDocs.length > 1 ? `
                <div class="doc-switcher">
                    <span class="doc-switcher-label">切换文档:</span>
                    <select id="docSwitcher" onchange="switchDocInModal(this.value)">
                        ${readyDocs.map(d => `<option value="${d.docId}" ${d.docId === docId ? 'selected' : ''}>${escapeHtml(d.name)}</option>`).join('')}
                    </select>
                </div>
                ` : ''}
                <button class="modal-close" onclick="closeAIModal()">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>
            <div class="ai-tabs">
                <button class="ai-tab active" data-tab="overview" onclick="switchAITab('overview')">文档概览</button>
                <button class="ai-tab" data-tab="qa" onclick="switchAITab('qa')">智能问答</button>
            </div>
            <div class="modal-body ai-body">
                <div class="tab-content active" id="tab-overview">
                    ${renderOverviewContent(aiStatus.representations, docId)}
                </div>
                <div class="tab-content" id="tab-qa">
                    <div class="qa-container">
                        <div class="qa-history" id="qaHistory">
                            ${renderQAHistory(docId)}
                        </div>
                        <div class="example-questions" id="exampleQuestions">
                            <span class="example-label">试试这样问:</span>
                            <button class="example-btn" onclick="askExample('这篇文章的主要内容是什么？')">主要内容</button>
                            <button class="example-btn" onclick="askExample('总结一下重点知识点')">重点知识点</button>
                            <button class="example-btn" onclick="askExample('有哪些关键结论？')">关键结论</button>
                        </div>
                        <div class="qa-input-area">
                            <input type="text" class="qa-input" id="qaInput" placeholder="输入问题...">
                            <button class="qa-send-btn" id="qaSendBtn">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    // 使用 addEventListener 绑定发送按钮
    document.getElementById('qaSendBtn').addEventListener('click', () => sendQuestion(docId));

    // 使用 addEventListener 绑定 Enter 键
    document.getElementById('qaInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendQuestion(docId);
        }
    });

    // 点击背景关闭
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeAIModal();
    });

    // 加载对话历史
    loadQAHistory(docId);
}

// 切换模态框中的文档
function switchDocInModal(docId) {
    const fileData = Array.from(files.values()).find(f => f.docId === docId);
    if (fileData) {
        closeAIModal();
        openAIModal(docId, fileData.name);
    }
}

// 渲染 QA 历史
function renderQAHistory(docId) {
    const history = qaHistoryStore.get(docId) || [];
    if (history.length === 0) {
        return '<div class="qa-empty">开始提问吧！</div>';
    }
    return history.map(item => `
        <div class="qa-item user">
            <div class="qa-bubble user">${escapeHtml(item.question)}</div>
        </div>
        <div class="qa-item ai">
            <div class="qa-bubble ai">
                <div class="qa-answer">${item.answer || '抱歉，未找到相关答案。'}</div>
            </div>
        </div>
    `).join('');
}

// 加载对话历史
function loadQAHistory(docId) {
    try {
        const saved = localStorage.getItem(`qaHistory_${docId}`);
        if (saved) {
            const history = JSON.parse(saved);
            qaHistoryStore.set(docId, history);
            const qaHistory = document.getElementById('qaHistory');
            if (qaHistory) {
                qaHistory.innerHTML = renderQAHistory(docId);
            }
        }
    } catch (e) {
        console.error('加载对话历史失败:', e);
    }
}

// 保存对话历史
function saveQAHistory(docId) {
    try {
        const history = qaHistoryStore.get(docId) || [];
        // 限制每个文档最多保存20条
        const limited = history.slice(-20);
        localStorage.setItem(`qaHistory_${docId}`, JSON.stringify(limited));
    } catch (e) {
        console.error('保存对话历史失败:', e);
    }
}

// 示例问题
function askExample(question) {
    const input = document.getElementById('qaInput');
    if (input) {
        input.value = question;
        if (currentAIDocId) {
            sendQuestion(currentAIDocId);
        }
    }
}

// 切换 AI 标签页
function switchAITab(tabName) {
    document.querySelectorAll('.ai-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `tab-${tabName}`);
    });
}

// 渲染概览内容（带骨架屏）
function renderOverviewContent(representations, docId) {
    let html = '<div class="overview-container">';

    // 使用骨架屏
    html += `
        <div class="overview-section" id="overviewFullText">
            <h4 class="overview-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                全文摘要
            </h4>
            <div class="overview-content">
                <div class="skeleton skeleton-text"></div>
                <div class="skeleton skeleton-text"></div>
                <div class="skeleton skeleton-text"></div>
            </div>
        </div>
        <div class="overview-section" id="overviewStructure">
            <h4 class="overview-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
                文档结构
            </h4>
            <div class="overview-toc">
                <div class="skeleton skeleton-text" style="width: 80%"></div>
                <div class="skeleton skeleton-text" style="width: 60%"></div>
                <div class="skeleton skeleton-text" style="width: 70%"></div>
            </div>
        </div>
        <div class="overview-section" id="overviewKnowledge">
            <h4 class="overview-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                知识点
            </h4>
            <div class="overview-knowledge">
                <div class="skeleton skeleton-text"></div>
                <div class="skeleton skeleton-text"></div>
            </div>
        </div>
    `;

    html += '</div>';

    // 异步加载详情
    setTimeout(() => {
        loadOverviewDetails(representations, docId);
    }, 100);

    return html;
}

// 加载概览详情
async function loadOverviewDetails(representations, docId) {
    const byType = representations.by_type || {};
    const samples = representations.samples || [];

    // 渲染全文摘要
    const fullTextSample = samples.find(s => s.rep_type === 'full_text');
    const fullTextEl = document.getElementById('overviewFullText');
    if (fullTextEl && fullTextSample) {
        const content = fullTextSample.content_preview || fullTextSample.content || '';
        fullTextEl.querySelector('.overview-content').innerHTML = `<pre class="content-preview">${escapeHtml(content)}</pre>`;
    }

    // 获取完整的结构表示
    try {
        const repsResp = await fetchWithRetry(`${DOC_BOT_API}/representations/${representations.doc_id || docId}`);
        if (repsResp.ok) {
            const reps = await repsResp.json();
            renderStructureAndKnowledge(reps);
        }
    } catch (e) {
        console.error('获取表示详情失败:', e);
        // 降级处理：用 samples 中的数据
        renderStructureAndKnowledgeFallback(samples);
    }
}

function renderStructureAndKnowledgeFallback(samples) {
    const structureEl = document.getElementById('overviewStructure');
    const knowledgeEl = document.getElementById('overviewKnowledge');

    // 从 samples 提取结构信息
    const structureSamples = samples.filter(s => s.rep_type === 'structure');
    if (structureEl && structureSamples.length > 0) {
        let tocHtml = '<div class="toc-tree">';
        structureSamples.slice(0, 5).forEach(s => {
            const title = s.title || s.metadata?.heading || '章节';
            tocHtml += `<div class="toc-item">${escapeHtml(title)}</div>`;
        });
        tocHtml += '</div>';
        structureEl.querySelector('.overview-toc').innerHTML = tocHtml;
    }

    // 从 samples 提取知识点
    const knowledgeSamples = samples.filter(s => s.rep_type === 'knowledge');
    if (knowledgeEl && knowledgeSamples.length > 0) {
        let knHtml = '<div class="knowledge-list">';
        knowledgeSamples.slice(0, 3).forEach(s => {
            const content = s.content_preview || s.content || '';
            knHtml += `<div class="knowledge-item">${escapeHtml(content.substring(0, 100))}</div>`;
        });
        knHtml += '</div>';
        knowledgeEl.querySelector('.overview-knowledge').innerHTML = knHtml;
    }
}

// 渲染结构和知识点
function renderStructureAndKnowledge(repsData) {
    const reps = repsData.representations || {};

    // 渲染目录结构
    const structureReps = reps.structure || [];
    const tocEl = document.getElementById('overviewStructure')?.querySelector('.overview-toc');
    if (tocEl && structureReps.length > 0) {
        let tocHtml = '<div class="toc-tree">';
        structureReps.forEach(doc => {
            const meta = doc.metadata || {};
            if (meta.structure_type === 'toc' && meta.heading_tree) {
                meta.heading_tree.forEach(h => {
                    tocHtml += `<div class="toc-item" style="padding-left: ${(h.level - 1) * 16}px">${escapeHtml(h.title)}</div>`;
                });
            }
        });
        tocHtml += '</div>';
        tocEl.innerHTML = tocHtml;
    } else {
        // 尝试降级
        renderStructureAndKnowledgeFallback(repsData.samples || []);
        return;
    }

    // 渲染知识点
    const knowledgeReps = reps.knowledge || [];
    const knEl = document.getElementById('overviewKnowledge')?.querySelector('.overview-knowledge');
    if (knEl && knowledgeReps.length > 0) {
        let knHtml = '<div class="knowledge-list">';
        knowledgeReps.forEach(doc => {
            const meta = doc.metadata || {};
            const content = doc.content_preview || '';
            if (meta.knowledge_type === 'conclusions') {
                knHtml += `<div class="knowledge-item"><strong>关键结论:</strong> ${escapeHtml(content)}</div>`;
            } else if (meta.knowledge_type === 'terms') {
                const terms = meta.terms || [];
                if (terms.length > 0) {
                    knHtml += `<div class="knowledge-item"><strong>专业术语:</strong> ${terms.map(t => `<code>${escapeHtml(t)}</code>`).join(', ')}</div>`;
                }
            } else if (meta.knowledge_type === 'key_points') {
                knHtml += `<div class="knowledge-item"><strong>关键要点:</strong> ${escapeHtml(content)}</div>`;
            }
        });
        knHtml += '</div>';
        knEl.innerHTML = knHtml;
    }
}

// 发送问题
async function sendQuestion(docId) {
    const input = document.getElementById('qaInput');
    const question = input.value.trim();
    if (!question) return;

    const qaHistory = document.getElementById('qaHistory');
    const aiStatus = aiProcessedDocs.get(docId);

    // 添加用户问题
    if (qaHistory.querySelector('.qa-empty')) {
        qaHistory.innerHTML = '';
    }

    const userQ = document.createElement('div');
    userQ.className = 'qa-item user';
    userQ.innerHTML = `<div class="qa-bubble user">${escapeHtml(question)}</div>`;
    qaHistory.appendChild(userQ);

    input.value = '';
    input.disabled = true;

    // 添加 AI 思考中（带打字机动画）
    const aiA = document.createElement('div');
    aiA.className = 'qa-item ai';
    aiA.innerHTML = `<div class="qa-bubble ai thinking"><div class="typing-dots"><span></span><span></span><span></span></div> 思考中...</div>`;
    qaHistory.appendChild(aiA);
    qaHistory.scrollTop = qaHistory.scrollHeight;

    // 获取对话历史用于多轮对话
    const history = qaHistoryStore.get(docId) || [];
    const conversationHistory = history.map(h => ({ question: h.question, answer: h.answer }));

    try {
        const response = await fetchWithRetry(`${DOC_BOT_API}/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: question,
                doc_id: docId,
                k: 3,
                use_context: true
            })
        });

        if (!response.ok) {
            throw new Error(`请求失败: ${response.status}`);
        }

        const result = await response.json();
        if (!result) {
            throw new Error('返回数据为空');
        }

        const answer = result.answer || '';
        const results = result.retrieval_results || [];

        // 移除思考中
        aiA.remove();

        // 添加 AI 回答
        const aiR = document.createElement('div');
        aiR.className = 'qa-item ai';

        let answerHtml = '<div class="qa-bubble ai">';
        if (answer) {
            // 格式化答案文本，识别代码块
            const formattedAnswer = formatAnswerText(answer);
            answerHtml += `<div class="qa-answer">${formattedAnswer}</div>`;
        }
        if (results.length > 0) {
            answerHtml += `<div class="qa-references">`;
            results.forEach((r, idx) => {
                answerHtml += `
                    <div class="qa-reference">
                        <div class="ref-source">
                            <span class="ref-type">${getRepTypeName(r.rep_type)}</span>
                            <span class="ref-title">${escapeHtml(r.title || '未知标题')}</span>
                            <span class="ref-page">页码: ${r.page_num || '?'}</span>
                        </div>
                        <div class="ref-content">${escapeHtml((r.content || '').substring(0, 150))}${(r.content || '').length > 150 ? '...' : ''}</div>
                    </div>
                `;
            });
            answerHtml += `</div>`;
        }
        if (!answer && results.length === 0) {
            answerHtml += '<div class="qa-answer">抱歉，未找到相关答案。</div>';
        }
        answerHtml += '</div>';
        aiR.innerHTML = answerHtml;
        qaHistory.appendChild(aiR);
        qaHistory.scrollTop = qaHistory.scrollHeight;

        // 保存到历史
        if (!qaHistoryStore.has(docId)) {
            qaHistoryStore.set(docId, []);
        }
        qaHistoryStore.get(docId).push({ question, answer: answerHtml, timestamp: Date.now() });
        saveQAHistory(docId);

    } catch (error) {
        aiA.querySelector('.qa-bubble').innerHTML = `<div class="error-specific">查询失败: ${error.message}</div>`;
        aiA.querySelector('.qa-bubble').classList.remove('thinking');
    } finally {
        input.disabled = false;
        input.focus();
    }
}

// 获取表示类型中文名
function getRepTypeName(type) {
    const names = {
        'full_text': '摘要',
        'chunk': '正文',
        'structure': '结构',
        'knowledge': '知识点'
    };
    return names[type] || type;
}

// 关闭 AI 模态框
function closeAIModal() {
    const modal = document.getElementById('aiModal');
    if (modal) {
        modal.classList.add('closing');
        setTimeout(() => modal.remove(), 200);
    }
    currentAIDocId = null;
}

// 查看文档内容
async function viewContent(docId, filename) {
    try {
        const response = await fetchWithRetry(`${API_BASE}/documents/${docId}/content`);
        const result = await response.json();
        showContentModal(docId, filename, result.content);
    } catch (error) {
        showToast('获取文档内容失败', 'error');
        console.error(error);
    }
}

// 下载文档内容
function downloadContent(docId, filename) {
    window.open(`${API_BASE}/documents/${docId}/download?format=md`, '_blank');
}

// 导出文档
async function handleExport(docId, filename, format) {
    try {
        showToast(`正在导出为 ${getFormatName(format)}...`, 'info');

        const response = await fetchWithRetry(`${API_BASE}/export/convert`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ doc_id: docId, format: format })
        }, 2);

        const result = await response.json();

        if (result.success && result.download_url) {
            showToast(`导出成功，开始下载...`, 'success');
            // 触发下载
            window.open(result.download_url, '_blank');
        } else {
            showToast(result.error || '导出失败', 'error');
        }
    } catch (error) {
        console.error('Export error:', error);
        showToast('导出失败: ' + error.message, 'error');
    }

    // 关闭下拉菜单
    closeAllExportDropdowns();
}

// 获取格式名称
function getFormatName(format) {
    const names = {
        'docx': 'Word 文档',
        'pdf': 'PDF 文档',
        'html': 'HTML 网页',
        'txt': '纯文本'
    };
    return names[format] || format;
}

// 关闭所有导出下拉菜单
function closeAllExportDropdowns() {
    document.querySelectorAll('.export-dropdown').forEach(d => {
        d.classList.remove('show');
    });
}

// 点击其他地方关闭下拉菜单
document.addEventListener('click', (e) => {
    if (!e.target.closest('.export-btn')) {
        closeAllExportDropdowns();
    }
});

// 导出按钮点击事件
document.addEventListener('click', (e) => {
    const exportBtn = e.target.closest('.export-btn');
    if (exportBtn) {
        e.stopPropagation();
        const dropdown = exportBtn.querySelector('.export-dropdown');
        if (dropdown) {
            // 关闭其他下拉菜单
            document.querySelectorAll('.export-dropdown').forEach(d => {
                if (d !== dropdown) d.classList.remove('show');
            });
            dropdown.classList.toggle('show');
        }
    }
});

// 显示内容弹窗
function showContentModal(docId, filename, content) {
    const existing = document.getElementById('contentModal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'contentModal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h3>${escapeHtml(filename)}</h3>
                <button class="modal-close" onclick="closeContentModal()">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>
            <div class="modal-body">
                <pre class="content-preview">${escapeHtml(content)}</pre>
            </div>
            <div class="modal-footer">
                <button class="btn-primary" onclick="downloadContent('${docId}', '${escapeHtml(filename)}')">下载 Markdown</button>
                <button class="btn-secondary" onclick="closeContentModal()">关闭</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeContentModal();
    });
}

function closeContentModal() {
    const modal = document.getElementById('contentModal');
    if (modal) {
        modal.classList.add('closing');
        setTimeout(() => modal.remove(), 200);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 格式化答案文本，识别并高亮代码块
function formatAnswerText(text) {
    if (!text) return '';

    // 如果包含代码块标记 ```，则处理代码块
    if (text.includes('```')) {
        // 分割代码块和普通文本
        const parts = [];
        let current = text;
        let codeBlockCount = 0;

        while (current.includes('```')) {
            const codeStart = current.indexOf('```');
            const codeEnd = current.indexOf('```', codeStart + 3);

            if (codeEnd === -1) {
                // 没有闭合标签，剩下的都是普通文本
                parts.push({ type: 'text', content: escapeHtml(current) });
                break;
            }

            // 提取代码块前的普通文本
            if (codeStart > 0) {
                parts.push({ type: 'text', content: escapeHtml(current.substring(0, codeStart)) });
            }

            // 提取代码块内容
            const codeContent = current.substring(codeStart + 3, codeEnd);
            // 检测语言
            const lines = codeContent.split('\n');
            let language = '';
            let code = codeContent;
            if (lines[0] && /^[a-zA-Z]+$/.test(lines[0])) {
                language = lines[0];
                code = lines.slice(1).join('\n');
            }
            parts.push({ type: 'code', language: language, content: code });

            // 继续处理剩下的内容
            current = current.substring(codeEnd + 3);
        }

        // 处理剩下的普通文本
        if (current) {
            parts.push({ type: 'text', content: escapeHtml(current) });
        }

        // 组合 HTML
        return parts.map(part => {
            if (part.type === 'code') {
                const langClass = part.language ? ` class="language-${part.language}"` : '';
                return `<pre${langClass}><code>${escapeHtml(part.content)}</code></pre>`;
            }
            return part.content;
        }).join('');

    } else {
        // 普通文本，直接 HTML 转义
        return escapeHtml(text);
    }
}

// 获取状态文字
function getStatusText(status) {
    const texts = {
        'pending': '等待中',
        'uploading': '上传中',
        'processing': '处理中',
        'done': '已完成',
        'error': '失败'
    };
    return texts[status] || status;
}

// 更新文件状态
function updateFileStatus(fileId, status, docId = null, errorType = null) {
    const fileData = files.get(fileId);
    if (fileData) {
        fileData.status = status;
        if (docId) fileData.docId = docId;
        if (errorType) fileData.errorType = errorType;
        console.log('[DEBUG] updateFileStatus:', fileId, status, 'errorType:', errorType);
        renderFileList();
    } else {
        console.log('[DEBUG] updateFileStatus: fileData not found for fileId:', fileId);
    }
}

// 处理队列
async function processQueue() {
    if (isProcessing || uploadQueue.length === 0) return;

    isProcessing = true;
    const fileId = uploadQueue.shift();
    const fileData = files.get(fileId);

    if (!fileData) {
        isProcessing = false;
        processQueue();
        return;
    }

    try {
        await uploadFile(fileData);
    } catch (error) {
        console.error('上传失败:', error);
        let errorType = null;
        if (error.message === 'FILE_TOO_LARGE') {
            errorType = 'FILE_TOO_LARGE';
        }
        updateFileStatus(fileId, 'error', null, errorType);
        showToast(`上传失败: ${fileData.name}`, 'error');
    }

    isProcessing = false;
    processQueue();
}

// 上传文件
async function uploadFile(fileData) {
    updateFileStatus(fileData.id, 'uploading');

    const formData = new FormData();
    formData.append('file', fileData.file);

    try {
        const response = await fetchWithRetry(`${API_BASE}/documents/upload`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();
        updateFileStatus(fileData.id, 'processing', result.doc_id);

        // 显示处理进度
        showProgress(fileData.name);

        // 轮询处理状态
        const pollResult = await pollDocumentStatus(fileData.id, result.doc_id);

        if (pollResult.success) {
            // 成功后检查是否自动 AI 处理
            if (autoAIProcessing) {
                await startAIProcessing(result.doc_id, fileData.name);
            }
        }
        // pollResult.success === false 时，pollDocumentStatus 内部已处理状态更新

    } catch (error) {
        // 上传失败时更新状态为 error
        updateFileStatus(fileData.id, 'error', null, 'UPLOAD_ERROR');
        showToast(`上传失败: ${error.message}`, 'error');
        throw error;
    }
}

// 显示处理进度
function showProgress(filename) {
    progressArea.style.display = 'block';
    progressFilename.textContent = filename;
    progressStatus.textContent = '正在上传...';
    progressFill.style.width = '5%';
}

// 更新处理进度
function updateProgress(percent, status) {
    progressFill.style.transition = 'width 0.5s ease';
    progressFill.style.width = percent + '%';
    progressStatus.textContent = status;
}

// 轮询文档状态
async function pollDocumentStatus(fileId, docId) {
    const maxAttempts = 120;
    const slowWarningTime = 45; // 1.5分钟提示 (45 * 2秒 = 90秒)
    const timeoutTime = 90; // 3分钟超时 (90 * 2秒 = 180秒)
    let attempts = 0;
    let slowWarningShown = false;
    let timeoutShown = false;

    const poll = async () => {
        attempts++;

        try {
            const response = await fetchWithRetry(`${API_BASE}/documents/${docId}/status`);

            if (!response.ok) {
                throw new Error('获取状态失败');
            }

            const result = await response.json();

            // 处理完成状态 (原 'ready' 现改为 'completed')
            if (result.status === 'completed' || result.status === 'ready') {
                updateProgress(100, '处理完成!');
                updateFileStatus(fileId, 'done');
                addToHistory(files.get(fileId));
                setTimeout(() => {
                    progressArea.style.display = 'none';
                }, 1500);
                showToast('文档处理完成!', 'success');
                return { success: true, warnings: result.warnings || [] };
            }

            // 处理失败状态 - 显示错误信息
            if (result.status === 'failed') {
                updateProgress(100, '处理失败');
                const errorMsg = result.error || '文档处理失败，请检查文件格式或重试';
                updateFileStatus(fileId, 'error', null, 'PROCESSING_ERROR');
                showToast(`处理失败: ${errorMsg}`, 'error');
                progressArea.style.display = 'none';

                // 将错误信息存储到文件数据中，便于查看详情
                const fileData = files.get(fileId);
                if (fileData) {
                    fileData.errorMessage = errorMsg;
                }
                return { success: false, error: errorMsg };
            }

            // 处理超时状态
            if (result.status === 'timeout') {
                updateProgress(100, '处理超时');
                const errorMsg = result.error || '文档处理超时，请重试或联系支持';
                updateFileStatus(fileId, 'error', null, 'PROCESSING_TIMEOUT');
                showToast(`处理超时: ${errorMsg}`, 'error');
                progressArea.style.display = 'none';

                const fileData = files.get(fileId);
                if (fileData) {
                    fileData.errorMessage = errorMsg;
                }
                return { success: false, error: errorMsg };
            }

            // 处理中状态
            if (result.status === 'processing' || result.status === 'pending' || result.status === 'running') {
                lastProgress = Math.min(85, 10 + Math.floor(attempts * 0.5));
                let statusText;
                if (attempts >= timeoutTime && !timeoutShown) {
                    statusText = '处理较慢，请耐心等待...';
                    timeoutShown = true;
                    progressStatus.classList.add('timeout-warning');
                } else if (attempts >= slowWarningTime && !slowWarningShown) {
                    statusText = '正在处理中...';
                    slowWarningShown = true;
                } else if (attempts < 10) {
                    statusText = '正在解析文档...';
                } else if (attempts < 30) {
                    statusText = '正在识别文字内容...';
                } else if (attempts < 60) {
                    statusText = '正在处理中...';
                } else {
                    statusText = '处理较慢，请耐心等待...';
                }
                updateProgress(lastProgress, statusText);
            }

            if (attempts >= maxAttempts) {
                updateFileStatus(fileId, 'error', null, 'PROCESSING_TIMEOUT');
                showToast('处理超时，请重试', 'error');
                progressArea.style.display = 'none';
                return { success: false, error: 'Processing timeout' };
            }

            setTimeout(poll, 2000);

        } catch (error) {
            if (attempts >= maxAttempts) {
                updateFileStatus(fileId, 'error', null, 'NETWORK_ERROR');
                showToast('处理失败，请重试', 'error');
                progressArea.style.display = 'none';
                return { success: false, error: error.message };
            } else {
                setTimeout(poll, 2000);
            }
        }
    };

    let lastProgress = 10;
    updateProgress(10, '正在解析文档...');
    setTimeout(poll, 2000);

    // 等待轮询完成
    return new Promise(resolve => {
        const checkDone = setInterval(() => {
            const fileData = files.get(fileId);
            if (fileData && (fileData.status === 'done' || fileData.status === 'error')) {
                clearInterval(checkDone);
                resolve({ success: fileData.status === 'done', error: fileData.errorMessage });
            }
        }, 500);
    });
}

// 添加到历史记录
function addToHistory(fileData) {
    const existingItems = historyList.querySelectorAll('.history-item');
    for (const item of existingItems) {
        if (item.dataset.docId === fileData.docId) {
            return;
        }
    }

    const emptyState = historyList.querySelector('.empty-state');
    if (emptyState) {
        emptyState.remove();
    }

    const historyItem = createHistoryItem(fileData.docId, fileData.name, '刚刚');

    historyList.insertBefore(historyItem, historyList.firstChild);

    saveHistory(fileData);
}

// 创建历史记录项
function createHistoryItem(docId, name, time) {
    const historyItem = document.createElement('div');
    historyItem.className = 'history-item';
    historyItem.dataset.docId = docId;

    const ext = name.split('.').pop().toLowerCase();
    let iconClass = 'history-icon';
    if (['pdf'].includes(ext)) iconClass += ' pdf';
    else if (['doc', 'docx'].includes(ext)) iconClass += ' doc';
    else if (['xlsx', 'xls'].includes(ext)) iconClass += ' xlsx';
    else if (['png', 'jpg', 'jpeg'].includes(ext)) iconClass += ' img';
    else iconClass += ' txt';

    const aiStatus = aiProcessedDocs.get(docId);
    const aiStatusClass = aiStatus ? (aiStatus.status === 'ready' ? 'ai-ready' : 'ai-processing') : '';
    const aiStatusText = aiStatus ? (aiStatus.status === 'ready' ? '已就绪' : '处理中') : 'AI处理';

    historyItem.innerHTML = `
        <span class="${iconClass}">${getFileIcon(name)}</span>
        <div class="history-info">
            <div class="history-name">${escapeHtml(name)}</div>
            <div class="history-time">${time}</div>
        </div>
        <button class="action-btn ai-btn ${aiStatusClass}" onclick="handleAIAction('${docId}', '${escapeHtml(name)}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2a10 10 0 1 0 10 10H12V2z"/><path d="M12 2a10 10 0 0 1 10 10"/></svg>
            ${aiStatusText}
        </button>
        <button class="action-btn view-btn" onclick="viewContent('${docId}', '${escapeHtml(name)}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            查看
        </button>
        <button class="action-btn download-btn" onclick="downloadContent('${docId}', '${escapeHtml(name)}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            下载
        </button>
        <div class="action-btn export-btn" style="position:relative;">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            导出
            <div class="export-dropdown" id="exportDropdown_hist_${docId}">
                <button class="export-dropdown-item" onclick="handleExport('${docId}', '${escapeHtml(name)}', 'docx')">
                    <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    Word 文档
                </button>
                <button class="export-dropdown-item" onclick="handleExport('${docId}', '${escapeHtml(name)}', 'pdf')">
                    <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
                    PDF 文档
                </button>
                <div class="export-dropdown-divider"></div>
                <button class="export-dropdown-item" onclick="handleExport('${docId}', '${escapeHtml(name)}', 'html')">
                    <svg viewBox="0 0 24 24"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
                    HTML 网页
                </button>
                <button class="export-dropdown-item" onclick="handleExport('${docId}', '${escapeHtml(name)}', 'txt')">
                    <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                    纯文本
                </button>
            </div>
        </div>
    `;
    return historyItem;
}

// 从本地存储加载历史记录
function loadHistory() {
    try {
        const history = localStorage.getItem('uploadHistory');
        if (history) {
            const items = JSON.parse(history);
            if (items.length > 0) {
                const emptyState = historyList.querySelector('.empty-state');
                if (emptyState) emptyState.remove();

                items.forEach(item => {
                    const historyItem = createHistoryItem(item.docId, item.name, item.time);
                    historyList.appendChild(historyItem);
                });
            }
        }
    } catch (e) {
        console.error('加载历史记录失败:', e);
    }
}

// 保存到本地存储
function saveHistory(fileData) {
    try {
        let history = [];
        const existing = localStorage.getItem('uploadHistory');
        if (existing) {
            history = JSON.parse(existing);
        }

        history.unshift({
            docId: fileData.docId,
            name: fileData.name,
            time: new Date().toLocaleString('zh-CN')
        });

        history = history.slice(0, 10);

        localStorage.setItem('uploadHistory', JSON.stringify(history));
    } catch (e) {
        console.error('保存历史记录失败:', e);
    }
}

// 初始化
function init() {
    initAutoProcessSwitch();
    loadHistory();
}

// 启动
init();
