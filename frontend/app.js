// API 基础 URL（自动检测，与前端同源）
const API_BASE = '/api/v1';

// DOM 元素
const taskForm = document.getElementById('task-form');
const taskInput = document.getElementById('task-input');
const threadIdInput = document.getElementById('thread-id');
const submitBtn = document.getElementById('submit-btn');
const clearBtn = document.getElementById('clear-btn');
const outputSection = document.getElementById('output-section');
const outputDiv = document.getElementById('output');
const errorSection = document.getElementById('error-section');
const healthStatus = document.getElementById('health-status');
const toolsStatus = document.getElementById('tools-status');

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    loadHealthStatus();
    loadTools();
    
    taskForm.addEventListener('submit', handleSubmit);
    clearBtn.addEventListener('click', handleClear);
});

// 处理表单提交
async function handleSubmit(e) {
    e.preventDefault();
    
    const input = taskInput.value.trim();
    if (!input) {
        showError('请输入任务描述');
        return;
    }

    // 禁用提交按钮
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="loading" role="status" aria-label="加载中"></span> 执行中…';
    
    // 清空之前的输出和错误
    errorSection.innerHTML = '';
    outputDiv.textContent = '';
    outputSection.style.display = 'block';

    try {
        const response = await fetch(`${API_BASE}/tasks/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                input: input,
                thread_id: threadIdInput.value.trim() || null,
                stream: false,
            }),
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP ${response.status}`);
        }

        const result = await response.json();
        displayResult(result);
        
        // 保存 thread_id 以便继续对话
        if (result.thread_id && !threadIdInput.value) {
            threadIdInput.value = result.thread_id;
        }

    } catch (error) {
        showError(`任务执行失败: ${error.message}`);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '提交任务';
    }
}

// 显示结果
function displayResult(result) {
    const output = [];
    
    output.push('=== 执行结果 ===\n');
    output.push(`会话 ID: ${result.thread_id}\n`);
    output.push(`反思轮次: ${result.reflection_round}\n`);
    output.push(`评分: ${result.critic_score.toFixed(2)}\n`);
    output.push(`消息数: ${result.message_count}\n`);
    
    if (result.plan) {
        output.push('\n--- 执行计划 ---\n');
        output.push(result.plan);
        output.push('\n');
    }
    
    if (result.output) {
        output.push('\n--- 最终输出 ---\n');
        output.push(result.output);
    }
    
    outputDiv.textContent = output.join('');
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
    outputSection.style.display = 'none';
    errorSection.innerHTML = '';
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
