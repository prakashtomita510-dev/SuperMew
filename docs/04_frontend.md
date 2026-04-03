# 04. 前端详解

## 4.1 技术栈

前端不是工程化构建产物，而是静态页面直接依赖 CDN：

- Vue 3 CDN
- marked
- highlight.js
- Google Fonts
- Font Awesome

入口文件：

- `frontend/index.html`
- `frontend/script.js`
- `frontend/style.css`

部署方式：

- 由 FastAPI 通过 `StaticFiles` 直接托管

## 4.2 页面结构

主界面由三部分组成：

1. 左侧侧边栏
- 新建会话
- 历史记录
- 设置（仅管理员）
- 清空当前对话
- 当前用户显示
- 退出登录

2. 主内容区
- 未登录时显示登录/注册面板
- 登录后显示聊天区或设置区

3. 浮层/弹窗
- 历史会话右侧抽屉
- 引用详情弹窗

## 4.3 状态模型

`frontend/script.js` 的核心状态包括：

- `messages`
- `userInput`
- `isLoading`
- `abortController`
- `sessionId`
- `sessions`
- `documents`
- `selectedFile`
- `token`
- `currentUser`
- `authMode`
- `activeCitation`
- `isDragOver`

认证相关计算属性：

- `isAuthenticated`
- `isAdmin`

## 4.4 登录与鉴权流程

实现方式：

1. 登录/注册直接 `fetch('/auth/login')` 或 `fetch('/auth/register')`
2. 成功后拿到 `access_token`
3. 保存到 `localStorage`
4. 后续通过 `authHeaders()` 自动带上 `Authorization: Bearer <token>`
5. 页面刷新后在 `mounted()` 中调用 `/auth/me` 恢复用户态

特点：

- 简单直接
- 适合单页应用

局限：

- token 只存在本地浏览器存储
- 没有 refresh token
- 401 时直接 `handleLogout()`

## 4.5 聊天流程

### 发送消息

`handleSend()` 做了这些事：

1. 校验登录态
2. 把用户消息先插入本地 `messages`
3. 追加一个空的 bot 占位消息，带 `isThinking: true`
4. 创建 `AbortController`
5. 请求 `/chat/stream`
6. 用 `ReadableStream` 手动解析 SSE

### 解析 SSE

前端支持 4 类事件：

- `content`
- `trace`
- `rag_step`
- `error`

处理逻辑：

- `content`：追加到 bot 消息正文
- `trace`：挂到 `msg.ragTrace`
- `rag_step`：追加到 `msg.ragSteps`
- `error`：直接插入错误文本

### 停止回答

`handleStop()` 会执行：

- `this.abortController.abort()`

用户体验上：

- 若还没拿到正文，显示“已终止回答”
- 若已拿到部分正文，追加“回答已被终止”

## 4.6 历史会话

### 读取

- `handleHistory()` 调 `/sessions`
- `loadSession(sessionId)` 调 `/sessions/{sessionId}`

### 删除

- `deleteSession(sessionId)` 调 DELETE `/sessions/{sessionId}`

### 本地表现

- 会话标题当前直接显示 `session_id`
- 新会话 ID 是 `session_<timestamp>`

这意味着：

- 用户看见的是技术型会话名，不是自然语言摘要标题

## 4.7 文档管理

管理员才会看到“设置”入口。

功能包括：

- 文档列表查询
- 文件选择上传
- 拖拽上传
- 文档删除

交互细节：

- 上传后会立即刷新文档列表
- 前端只展示文件名、文件类型、chunk 数量

## 4.8 RAG 可视化

这是前端最有辨识度的部分之一。

### 思考中气泡

当 bot 还没正式输出正文时，前端会显示：

- 动态点动画
- 当前最新步骤标签
- 逐行堆叠的 `ragSteps`

### 结果详情折叠

回复完成后，如果有 `ragTrace`，会显示一个“检索过程”折叠面板。

当前模板尝试展示的字段很多，包括：

- 工具名
- 检索阶段
- 评分结果
- 重写策略
- 检索模式
- auto-merge 状态
- rerank 状态
- Step-Back 问题
- HyDE 文档
- 检索到的 chunk 列表

### 引用预览

正文中的 `[1]`、`[2]` 会被转成可点击元素。

点击后：

- `handleCitationClick()` 从 `msg.ragTrace.retrieved_chunks` 取对应 chunk
- 打开弹窗显示文件名、页码和原文片段

## 4.9 前端和后端的契约关系

当前前端依赖以下接口：

- `/auth/register`
- `/auth/login`
- `/auth/me`
- `/chat/stream`
- `/sessions`
- `/sessions/{id}`
- `/documents`
- `/documents/upload`
- `/documents/{filename}`

它还依赖一组隐含契约：

- SSE 事件必须以 `data: ...\n\n` 格式输出
- `ragTrace` 的结构要与前端模板字段一致
- bot 回复里的引用序号要与 `retrieved_chunks` 顺序一致

## 4.10 前端风险与限制

1. 完全依赖 CDN
- 离线或受限网络环境下会影响加载

2. 无构建流程
- 难以做模块化、类型检查和 lint

3. 全局事件委托
- `mounted()` 中直接在 `document` 上注册点击监听，长期可能带来维护成本

4. trace 字段不完全对齐
- 前端会尝试渲染 `tool_name`、`initial_retrieved_chunks`
- 后端当前并不稳定提供这些字段

5. 会话名不可读
- 直接使用时间戳 ID，不利于历史管理

## 4.11 适合后续演进的方向

- 把前端迁移到正式 Vue 工程
- 用 TypeScript 约束 `ragTrace` 与 API 返回契约
- 引入统一 API client
- 给会话生成标题
- 为文档上传增加进度与后台任务状态
