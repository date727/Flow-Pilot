# Flow-Pilot 前端 Demo

这是 Flow-Pilot 的简洁前端界面，用于与后端 API 交互。

## 特性

- ✅ 符合 Web Interface Guidelines 规范
- ✅ 完整的无障碍支持（ARIA 标签、键盘导航、屏幕阅读器友好）
- ✅ 响应式设计（移动端和桌面端）
- ✅ 深色模式自动适配
- ✅ 实时系统状态监控
- ✅ 工具列表展示
- ✅ 任务提交与结果展示
- ✅ 会话管理（支持多轮对话）

## 使用方法

### 1. 启动后端服务

确保后端服务已启动：

```bash
# 在项目根目录
python app/main.py
```

后端将在 `http://127.0.0.1:8000` 运行。

### 2. 打开前端

直接在浏览器中打开 `frontend/index.html` 文件，或使用本地服务器：

```bash
# 使用 Python 内置服务器
cd frontend
python -m http.server 8080
```

然后访问 `http://localhost:8080`

### 3. 使用界面

1. **提交任务**: 在"任务描述"框中输入您的任务
2. **会话 ID**: 可选，用于继续之前的对话（留空自动生成）
3. **查看结果**: 提交后在"执行结果"区域查看输出
4. **系统状态**: 右侧显示 Milvus、MCP 连接状态
5. **可用工具**: 右侧显示所有已连接的 MCP 工具

## 技术实现

### 符合 Web Interface Guidelines

本前端严格遵守 Vercel Web Interface Guidelines，包括：

#### 无障碍性
- 所有表单控件都有 `<label>` 标签
- 使用语义化 HTML（`<button>`, `<form>`, `<main>`, `<aside>`）
- 加载状态使用 `aria-label` 和 `role="status"`
- 错误消息使用 `role="alert"`
- 输出区域使用 `role="log"` 和 `aria-live="polite"`
- 包含跳转链接（skip link）

#### 焦点状态
- 所有交互元素都有 `:focus-visible` 样式
- 使用 `outline` 和 `box-shadow` 提供清晰的焦点指示

#### 表单
- 正确的 `autocomplete` 属性
- 禁用不必要的拼写检查（会话 ID）
- 提交按钮在请求期间显示加载状态
- 占位符使用 `…` 而非 `...`

#### 动画
- 使用 `@media (prefers-reduced-motion: reduce)` 提供无动画版本
- 仅动画 `transform` 和 `opacity`
- 明确列出过渡属性（无 `transition: all`）

#### 排版
- 使用 `…` 而非 `...`
- 加载状态文本以 `…` 结尾
- 使用 `text-wrap: balance` 优化标题
- 数字使用 `font-variant-numeric: tabular-nums`

#### 内容处理
- 文本容器使用 `word-break: break-words`
- 处理空状态（显示友好提示）
- 用户输入使用 HTML 转义防止 XSS

#### 触摸与交互
- 使用 `touch-action: manipulation` 消除双击缩放延迟
- 设置 `-webkit-tap-highlight-color: transparent`

#### 深色模式
- 在 `<html>` 上设置 `color-scheme: dark`
- 使用 CSS 变量支持主题切换
- 设置 `<meta name="theme-color">`

#### 安全区域
- 使用 `env(safe-area-inset-bottom)` 适配刘海屏

#### 性能
- 避免在渲染中读取布局
- 使用 Flexbox/Grid 而非 JS 测量

## API 端点

前端调用以下后端 API：

- `GET /health` - 健康检查
- `GET /api/v1/tools/` - 获取工具列表
- `POST /api/v1/tasks/` - 提交任务
- `GET /api/v1/tasks/{thread_id}` - 获取任务历史（未在 UI 中实现）

## 浏览器兼容性

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- 移动浏览器（iOS Safari, Chrome Mobile）

## 未来改进

- [ ] 流式输出支持（SSE）
- [ ] 任务历史查看
- [ ] 工具直接调用界面
- [ ] 更丰富的可视化（执行计划图表）
- [ ] 导出对话记录
