// ── Flow-Pilot Chat UI ──────────────────────────────────────────────────────
const API_BASE = '/api/v1';

// ── State ──────────────────────────────────────────────────────────────────
let state = {
    threads: [],           // 线程 ID 列表
    activeThreadId: null,  // 当前选中线程
    isStreaming: false,    // 是否正在流式接收
    controller: null,      // AbortController
};

// ── DOM refs ───────────────────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const threadList = $('#thread-list');
const chatMessages = $('#chat-messages');
const chatForm = $('#chat-form');
const chatInput = $('#chat-input');
const sendBtn = $('#send-btn');
const healthDot = $('#health-dot');
const healthStatus = $('#health-status');
const toolsStatus = $('#tools-status');

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadThreads();
    loadHealthStatus();
    loadTools();
    chatForm.addEventListener('submit', handleSend);
    $('#btn-new-chat').addEventListener('click', newChat);
    chatInput.addEventListener('input', autoResize);
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); chatForm.dispatchEvent(new Event('submit')); }
    });
});

function autoResize() {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    sendBtn.disabled = !chatInput.value.trim() || state.isStreaming;
}

// ── Thread List ────────────────────────────────────────────────────────────
async function loadThreads() {
    try {
        const res = await fetch(`${API_BASE}/tasks/`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        state.threads = Array.isArray(data) ? data : [];
        renderThreadList();
        // 自动选中第一个
        if (!state.activeThreadId && state.threads.length > 0) {
            selectThread(state.threads[0]);
        }
    } catch (err) {
        threadList.innerHTML = '<p class="empty">加载失败</p>';
    }
}

function renderThreadList() {
    if (state.threads.length === 0) {
        threadList.innerHTML = '<p class="empty">暂无对话</p>';
        return;
    }
    threadList.innerHTML = state.threads.map(tid => `
        <div class="thread-item${tid === state.activeThreadId ? ' active' : ''}"
             data-thread-id="${escapeAttr(tid)}"
             role="option"
             aria-selected="${tid === state.activeThreadId}">
            <span class="tid" title="${escapeAttr(tid)}">${shortId(tid)}</span>
        </div>
    `).join('');

    threadList.querySelectorAll('.thread-item').forEach(el => {
        el.addEventListener('click', () => selectThread(el.dataset.threadId));
    });
}

function shortId(id) {
    if (!id) return '';
    return id.length > 24 ? id.slice(0, 12) + '…' + id.slice(-8) : id;
}

async function selectThread(threadId) {
    state.activeThreadId = threadId;
    renderThreadList();
    await loadThreadHistory(threadId);
}

async function loadThreadHistory(threadId) {
    chatMessages.innerHTML = '<div class="empty-chat"><p>加载中<span class="loading-dot"></span><span class="loading-dot"></span><span class="loading-dot"></span></p></div>';
    try {
        const res = await fetch(`${API_BASE}/tasks/${threadId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        // 防止竞态：如果用户在加载期间切换了会话或新建了对话，丢弃本次结果
        if (state.activeThreadId !== threadId) return;
        const data = await res.json();
        renderMessages(data.messages || []);
    } catch (err) {
        if (state.activeThreadId !== threadId) return;
        chatMessages.innerHTML = `<div class="empty-chat"><p>加载失败: ${escapeHtml(err.message)}</p></div>`;
    }
}

function newChat() {
    state.activeThreadId = null;
    renderThreadList();
    chatMessages.innerHTML = '<div class="empty-chat"><p>新对话 — 输入你的第一个任务开始</p></div>';
    chatInput.value = '';
    chatInput.focus();
    sendBtn.disabled = true;
}

// ── Message Rendering ──────────────────────────────────────────────────────
function renderMessages(messages) {
    if (!messages || messages.length === 0) {
        chatMessages.innerHTML = '<div class="empty-chat"><p>暂无消息</p></div>';
        return;
    }
    chatMessages.innerHTML = '';
    messages.forEach(m => appendMessage(m, false));
    scrollToBottom();
}

function appendMessage(msg, scroll = true) {
    // 移除空状态提示
    const empty = chatMessages.querySelector('.empty-chat');
    if (empty) empty.remove();

    const row = document.createElement('div');
    const role = msg.role || 'assistant';

    if (role === 'tool') {
        row.className = 'msg-row tool';
        const tag = msg.name ? `<span class="tool-tag">${escapeHtml(msg.name)}</span>` : '';
        row.innerHTML = `<div class="msg-bubble">${tag}${escapeHtml(msg.content || '')}</div>`;
    } else {
        row.className = `msg-row ${role}`;
        let content = escapeHtml(msg.content || '');
        // 工具调用信息
        if (msg.tool_calls && msg.tool_calls.length > 0) {
            const tools = msg.tool_calls.map(tc => {
                const tname = typeof tc === 'object' ? (tc.name || tc.function?.name || '') : '';
                return `<span class="tool-tag">🔧 ${escapeHtml(tname)}</span>`;
            }).join('');
            content = tools + (content ? '\n' + content : '');
        }
        row.innerHTML = `<div class="msg-bubble">${content}</div>`;
    }

    chatMessages.appendChild(row);
    if (scroll) scrollToBottom();
    return row;
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    });
}

// ── Send Message ───────────────────────────────────────────────────────────
async function handleSend(e) {
    e.preventDefault();
    const input = chatInput.value.trim();
    if (!input || state.isStreaming) return;

    // Show user message
    appendMessage({ role: 'user', content: input });
    chatInput.value = '';
    autoResize();
    scrollToBottom();

    // Start streaming
    state.isStreaming = true;
    sendBtn.disabled = true;
    sendBtn.textContent = '…';

    if (state.controller) state.controller.abort();
    state.controller = new AbortController();

    // Add an assistant placeholder that will be updated
    const aiRow = appendMessage({ role: 'assistant', content: '' });
    const aiBubble = aiRow.querySelector('.msg-bubble');
    let aiContent = '';

    // Add inline progress
    const progressRow = document.createElement('div');
    progressRow.className = 'msg-row assistant';
    progressRow.innerHTML = `
        <div class="progress-inline" id="inline-progress">
            <span class="pi-step" data-node="planner">规划</span><span class="pi-arrow">→</span>
            <span class="pi-step" data-node="executor">执行</span><span class="pi-arrow">→</span>
            <span class="pi-step" data-node="tools">工具</span><span class="pi-arrow">→</span>
            <span class="pi-step" data-node="critic">评审</span>
        </div>`;
    chatMessages.appendChild(progressRow);
    const progSteps = progressRow.querySelectorAll('.pi-step');

    function setProg(node, cls) {
        progSteps.forEach(s => { if (s.dataset.node === node) s.classList.add(cls); });
    }

    let resultThreadId = null;

    try {
        const res = await fetch(`${API_BASE}/tasks/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                input: input,
                thread_id: state.activeThreadId || null,
                stream: true,
            }),
            signal: state.controller.signal,
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

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
                    switch (data.type) {
                        case 'node_start':
                            setProg(data.node, 'active');
                            break;
                        case 'token':
                            aiContent += data.content;
                            aiBubble.textContent = aiContent;
                            scrollToBottom();
                            break;
                        case 'node_end':
                            setProg(data.node, 'done');
                            break;
                        case 'done':
                            if (data.thread_id) resultThreadId = data.thread_id;
                            break;
                        case 'error':
                            aiContent += `\n\n❌ ${data.message}`;
                            aiBubble.textContent = aiContent;
                            break;
                    }
                } catch (_) { /* skip malformed */ }
            }
        }

        // Remove progress bar
        progressRow.remove();

        // If no content came through, show fallback
        if (!aiContent.trim()) {
            aiBubble.textContent = '(无输出)';
        }

        // Update thread list and reload full history for refined output
        if (resultThreadId) {
            state.activeThreadId = resultThreadId;
            if (!state.threads.includes(resultThreadId)) {
                state.threads.unshift(resultThreadId);
            }
            renderThreadList();
            // Reload to get final refined output (after Critic, tool messages, etc.)
            await loadThreadHistory(resultThreadId);
        }

    } catch (err) {
        if (err.name !== 'AbortError') {
            progressRow.remove();
            aiBubble.textContent = aiContent + `\n\n❌ 执行失败: ${err.message}`;
        }
    } finally {
        state.isStreaming = false;
        sendBtn.textContent = '发送';
        sendBtn.disabled = !chatInput.value.trim();
        state.controller = null;
    }
}

// ── Health & Tools ─────────────────────────────────────────────────────────
async function loadHealthStatus() {
    try {
        const res = await fetch('/health');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const svc = data.services || {};
        const redisOk = (svc.redis || '').includes('connected');
        const milvusOk = (svc.milvus || '').includes('connected');

        healthDot.className = 'dot' + (redisOk ? '' : ' offline');

        healthStatus.innerHTML = `
            <div class="status-row"><span>Redis</span><span class="status-dot ${redisOk ? 'ok' : 'warn'}"></span> ${svc.redis || '?'}</div>
            <div class="status-row"><span>Milvus</span><span class="status-dot ${milvusOk ? 'ok' : 'warn'}"></span> ${svc.milvus || '?'}</div>
            <div class="status-row"><span>MCP</span><span>${svc.mcp_servers || '?'}</span></div>
        `;
    } catch (err) {
        healthDot.className = 'dot offline';
        healthStatus.innerHTML = '<p style="color:var(--error-color);font-size:0.8rem;">连接失败</p>';
    }
}

async function loadTools() {
    try {
        const res = await fetch(`${API_BASE}/tools/`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const tools = data.tools || [];
        if (tools.length === 0) {
            toolsStatus.innerHTML = '<p style="color:var(--text-tertiary);font-size:0.8rem;">暂无可用工具</p>';
            return;
        }
        toolsStatus.innerHTML = `
            <p style="font-size:0.75rem;color:var(--text-tertiary);margin-bottom:0.5rem;">共 ${tools.length} 个</p>
            <ul class="tool-list">${tools.map(t => {
                const fn = t.function || {};
                return `<li><div class="tname">${escapeHtml(fn.name || '?')}</div><div class="tdesc">${escapeHtml(fn.description || '')}</div></li>`;
            }).join('')}</ul>
        `;
    } catch (err) {
        toolsStatus.innerHTML = '<p style="color:var(--error-color);font-size:0.8rem;">加载失败</p>';
    }
}

// ── Helpers ────────────────────────────────────────────────────────────────
function escapeHtml(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = typeof s === 'string' ? s : JSON.stringify(s);
    return d.innerHTML;
}

function escapeAttr(s) {
    return (s || '').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
