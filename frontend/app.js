// API 基础 URL（自动检测，与前端同源）
const API_BASE = '/api/v1';

// DOM 元素
const taskForm = document.getElementById('task-form');
const taskInput = document.getElementById('task-input');
const threadIdInput = document.getElementById('thread-id');
const submitBtn = document.getElementById('submit-btn');
const clearBtn = document.getElementById('clear-btn');
const outputSection = document.getElementById('output-section');
const progressBar = document.getElementById('progress');
const streamOutput = document.getElementById('stream-output');
const outputDiv = document.getElementById('output');
const errorSection = document.getElementById('error-section');
const healthStatus = document.getElementById('health-status');
const toolsStatus = document.getElementById('tools-status');

let currentAbortController = null;

// 节点中文名
const NODE_LABELS = {
    planner: '规划',
    executor: '执行',
    tools: '工具',
    critic: '评审',
};

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    loadHealthStatus();
    loadTools();

    taskForm.addEventListener('submit', handleSubmit);
    clearBtn.addEventListener('click', handleClear);
});

// 重置进度条
function resetProgress() {
    progressBar.querySelectorAll('.step').forEach(el => {
        el.className = 'step';
    });
    streamOutput.textContent = '';
    outputDiv.textContent = '';
}

// 更新节点状态
function setNodeStatus(node, status) {
    const el = progressBar.querySelector(`[data-node="${node}"]`);
    if (!el) return;
    el.className = 'step';
    if (status === 'active') el.classList.add('active');
    else if (status === 'done') el.classList.add('done');
    else if (status === 'error') el.classList.add('error-step');
}

// 追加流式文本
function appendStream(text) {
    streamOutput.textContent += text;
    streamOutput.scrollTop = streamOutput.scrollHeight;
}

// 处理 SSE 事件
function handleSSEEvent(data) {
    switch (data.type) {
        case 'node_start':
            setNodeStatus(data.node, 'active');
            appendStream(`\n▶ ${NODE_LABELS[data.node] || data.node} 开始...\n`);
            break;

        case 'token':
            appendStream(data.content);
            break;

        case 'node_end':
            setNodeStatus(data.node, 'done');
            if (data.output) {
                appendStream(`\n✅ ${NODE_LABELS[data.node] || data.node} 完成\n`);
            }
            break;

        case 'done':
            appendStream('\n━━━ 全部完成 ━━━\n');
            break;

        case 'error':
            appendStream(`\n❌ 错误: ${data.message}\n`);
            showError(data.message);
            break;
    }
}

// 处理表单提交（流式）
async function handleSubmit(e) {
    e.preventDefault();

    const input = taskInput.value.trim();
    if (!input) {
        showError('请输入任务描述');
        return;
    }

    // 取消上一次请求
    if (currentAbortController) {
        currentAbortController.abort();
    }
    currentAbortController = new AbortController();

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="loading" role="status" aria-label="加载中"></span> 执行中…';

    errorSection.innerHTML = '';
    outputSection.style.display = 'block';
    resetProgress();

    try {
        const response = await fetch(`${API_BASE}/tasks/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                input: input,
                thread_id: threadIdInput.value.trim() || null,
                stream: true,
            }),
            signal: currentAbortController.signal,
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `HTTP ${response.status}`);
        }

        // 读取 SSE 流
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let threadId = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed || !trimmed.startsWith('data: ')) continue;

                try {
                    const data = JSON.parse(trimmed.slice(6));
                    handleSSEEvent(data);
                    if (data.type === 'done' && data.thread_id) {
                        threadId = data.thread_id;
                    }
                } catch (_) {
                    // 忽略非 JSON 行
                }
            }
        }

        // 流结束后获取最终结果
        if (threadId) {
            await loadFinalResult(threadId);
            if (!threadIdInput.value) {
                threadIdInput.value = threadId;
            }
        }

    } catch (error) {
        if (error.name !== 'AbortError') {
            showError(`任务执行失败: ${error.message}`);
        }
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '提交任务';
        currentAbortController = null;
    }
}

// 加载最终结果
async function loadFinalResult(threadId) {
    try {
        const response = await fetch(`${API_BASE}/tasks/${threadId}`);
        if (!response.ok) return;

        const result = await response.json();
        displayResult(result);
    } catch (_) {
        outputDiv.textContent = '(无法加载最终结果)';
    }
}

// 显示最终结果
function displayResult(result) {
    const output = [];

    output.push(`会话 ID: ${result.thread_id}`);
    output.push(`反思轮次: ${result.reflection_round}`);
    output.push(`评分: ${result.critic_score.toFixed(2)}`);
    output.push(`消息数: ${result.message_count}`);

    if (result.plan) {
        output.push('\n── 执行计划 ──\n');
        output.push(result.plan);
    }

    if (result.output) {
        output.push('\n── 最终输出 ──\n');
        output.push(result.output);
    }

    outputDiv.textContent = output.join('\n');
}

// 显示错误
function showError(message) {
    errorSection.innerHTML = `
        <div class="error-message" role="alert">
            <strong>错误:</strong> ${escapeHtml(message)}
        </div>
    `;
}

// 清空表单
function handleClear() {
    taskInput.value = '';
    threadIdInput.value = '';
    outputDiv.textContent = '';
    streamOutput.textContent = '';
    outputSection.style.display = 'none';
    errorSection.innerHTML = '';
    resetProgress();
    taskInput.focus();
}

// 加载健康状态
async function loadHealthStatus() {
    try {
        const response = await fetch('/health');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        displayHealthStatus(data);
    } catch (error) {
        healthStatus.innerHTML = `
            <p class="status-badge status-error">连接失败</p>
            <p style="margin-top: 0.5rem; font-size: 0.875rem; color: var(--text-secondary);">
                ${escapeHtml(error.message)}
            </p>
        `;
    }
}

// 显示健康状态
function displayHealthStatus(data) {
    const services = data.services || {};
    const html = [];

    html.push(`<p class="status-badge status-success">${data.status}</p>`);
    html.push('<div style="margin-top: 1rem; font-size: 0.875rem;">');

    html.push(`<p><strong>Redis:</strong> ${services.redis || 'unknown'}</p>`);
    html.push(`<p><strong>Milvus:</strong> ${services.milvus || 'unknown'}</p>`);
    html.push(`<p><strong>MCP:</strong> ${services.mcp_servers || 'unknown'}</p>`);

    html.push('</div>');
    healthStatus.innerHTML = html.join('');
}

// 加载工具列表
async function loadTools() {
    try {
        const response = await fetch(`${API_BASE}/tools/`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        displayTools(data);
    } catch (error) {
        toolsStatus.innerHTML = `
            <p class="empty-state">加载失败: ${escapeHtml(error.message)}</p>
        `;
    }
}

// 显示工具列表
function displayTools(data) {
    const tools = data.tools || [];

    if (tools.length === 0) {
        toolsStatus.innerHTML = '<p class="empty-state">暂无可用工具</p>';
        return;
    }

    const html = [];
    html.push(`<p style="margin-bottom: 1rem; font-size: 0.875rem; color: var(--text-secondary);">共 ${tools.length} 个工具</p>`);
    html.push('<ul class="tools-list">');

    tools.forEach(tool => {
        const fn = tool.function || {};
        html.push('<li class="tool-item">');
        html.push(`<div class="tool-name">${escapeHtml(fn.name || 'unknown')}</div>`);
        if (fn.description) {
            html.push(`<div class="tool-desc">${escapeHtml(fn.description)}</div>`);
        }
        html.push('</li>');
    });

    html.push('</ul>');
    toolsStatus.innerHTML = html.join('');
}

// HTML 转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
