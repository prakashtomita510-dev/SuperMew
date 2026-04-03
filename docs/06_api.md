# 06. API 说明

## 6.1 概览

当前 API 全部定义在 `backend/api.py`，没有版本前缀。

鉴权方式：

- Bearer Token
- 前端把 JWT 放在 `Authorization` 请求头中

角色：

- `user`
- `admin`

## 6.2 认证接口

### `POST /auth/register`

用途：

- 注册用户

权限：

- 匿名可调用

请求体：

```json
{
  "username": "alice",
  "password": "secret",
  "role": "user",
  "admin_code": null
}
```

说明：

- 若 `role=admin`，则必须提供正确 `admin_code`

响应：

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "username": "alice",
  "role": "user"
}
```

### `POST /auth/login`

用途：

- 登录并获取 JWT

权限：

- 匿名可调用

请求体：

```json
{
  "username": "alice",
  "password": "secret"
}
```

响应：

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "username": "alice",
  "role": "user"
}
```

### `GET /auth/me`

用途：

- 获取当前用户信息

权限：

- 已登录

响应：

```json
{
  "username": "alice",
  "role": "user"
}
```

## 6.3 聊天接口

### `POST /chat`

用途：

- 非流式聊天

权限：

- 已登录

请求体：

```json
{
  "message": "你好",
  "session_id": "session_1712345678"
}
```

响应：

```json
{
  "response": "你好呀",
  "rag_trace": {
    "tool_used": true
  }
}
```

说明：

- 当前前端默认不使用这个接口，而是使用 `/chat/stream`

### `POST /chat/stream`

用途：

- SSE 流式聊天

权限：

- 已登录

请求体：

```json
{
  "message": "解释一下 Transformer",
  "session_id": "session_1712345678"
}
```

响应类型：

- `text/event-stream`

事件格式：

#### 内容事件

```text
data: {"type":"content","content":"Transformer"}
```

#### 检索步骤事件

```text
data: {"type":"rag_step","step":{"icon":"🔍","label":"并行检索中...","detail":"执行 3 路查询"}}
```

#### trace 事件

```text
data: {"type":"trace","rag_trace":{...}}
```

#### 错误事件

```text
data: {"type":"error","content":"<error message>"}
```

#### 结束事件

```text
data: [DONE]
```

请求头建议：

- `Authorization: Bearer <token>`
- `Content-Type: application/json`

## 6.4 会话接口

### `GET /sessions`

用途：

- 获取当前用户的会话列表

权限：

- 已登录

响应：

```json
{
  "sessions": [
    {
      "session_id": "session_1712345678",
      "updated_at": "2026-04-02T12:00:00",
      "message_count": 8
    }
  ]
}
```

### `GET /sessions/{session_id}`

用途：

- 获取某个会话的消息详情

权限：

- 已登录，且只能访问自己的会话

响应：

```json
{
  "messages": [
    {
      "type": "human",
      "content": "你好",
      "timestamp": "2026-04-02T12:00:00",
      "rag_trace": null
    }
  ]
}
```

### `DELETE /sessions/{session_id}`

用途：

- 删除当前用户某个会话

权限：

- 已登录，且只能删除自己的会话

响应：

```json
{
  "session_id": "session_1712345678",
  "message": "成功删除会话"
}
```

## 6.5 文档接口

### `GET /documents`

用途：

- 获取知识库已上传文档列表

权限：

- `admin`

响应：

```json
{
  "documents": [
    {
      "filename": "attention-is-all-you-need-Paper.pdf",
      "file_type": "PDF",
      "chunk_count": 123
    }
  ]
}
```

说明：

- 当前 `chunk_count` 是基于 Milvus 中命中的 chunk 数量聚合得出

### `POST /documents/upload`

用途：

- 上传文档并完成入库

权限：

- `admin`

请求：

- `multipart/form-data`
- 字段名：`file`

允许类型：

- `.pdf`
- `.doc`
- `.docx`
- `.xls`
- `.xlsx`

响应：

```json
{
  "filename": "test.pdf",
  "chunks_processed": 12,
  "message": "成功上传并处理 test.pdf ..."
}
```

行为说明：

- 会先删除同名旧向量和旧父块
- 本地原始文件会重新写入 `data/documents/`

### `DELETE /documents/{filename}`

用途：

- 删除某文档对应的 Milvus 向量和父块记录

权限：

- `admin`

响应：

```json
{
  "filename": "test.pdf",
  "chunks_deleted": 12,
  "message": "成功删除文档 test.pdf 的向量数据（本地文件已保留）"
}
```

## 6.6 错误处理

聊天接口里有一层特殊处理：

- 若异常文本里包含 `Error code: 429`
- 会转成更明确的“上游模型服务限流/额度限制”

其他接口通常返回：

- `400` 参数错误
- `401` 未认证
- `403` 权限不足
- `404` 资源不存在
- `500` 服务内部错误

## 6.7 当前 API 设计特点

优点：

- 路由数量少，理解成本低
- 认证、聊天、文档管理边界明确
- SSE 事件结构简单，前端实现直接

不足：

- 没有版本管理
- `/auth/login` 与 `OAuth2PasswordBearer` 约定不完全一致
- 文档上传是同步阻塞式调用
- 没有健康检查接口
- 没有专门的知识库检索调试接口
