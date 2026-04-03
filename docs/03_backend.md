# 03. 后端详解

## 3.1 Web 入口

### `backend/app.py`

职责：

- 创建 FastAPI 应用
- 注册 startup 建表逻辑
- 注册 CORS
- 注册 no-cache 中间件
- 注册 API Router
- 把 `frontend/` 静态目录挂到根路径

输入输出：

- 输入：环境变量 `HOST`、`PORT`
- 输出：FastAPI `app`

依赖：

- `api.py`
- `database.init_db`
- `fastapi.staticfiles.StaticFiles`

关键点：

- `app.include_router(api_module.router)`
- `app.mount("/", StaticFiles(..., html=True), name="static")`

风险点：

- 使用 `import api as api_module` 和 `from database import init_db`，导致 `uvicorn backend.app:app` 无法正常导入
- CORS 配置为 `allow_origins=["*"]` 且 `allow_credentials=True`，浏览器语义和安全性都不理想

## 3.2 API 层

### `backend/api.py`

职责：

- 提供用户认证、聊天、会话管理、文档管理接口
- 组装文档处理所需对象
- 负责 HTTP 层异常转译

模块级单例：

- `loader = DocumentLoader()`
- `parent_chunk_store = ParentChunkStore()`
- `milvus_manager = MilvusManager()`
- `embedding_service = EmbeddingService()`
- `milvus_writer = MilvusWriter(...)`

这意味着导入 `api.py` 时就已经决定了很多依赖实例。

#### 认证接口

- `/auth/register`
- `/auth/login`
- `/auth/me`

职责：

- 用户注册、登录、获取当前用户信息

依赖：

- `auth.py`
- `models.User`

#### 会话接口

- `/sessions`
- `/sessions/{session_id}`
- `DELETE /sessions/{session_id}`

职责：

- 获取会话列表
- 获取会话消息
- 删除会话

依赖：

- `agent.storage`

#### 聊天接口

- `/chat`
- `/chat/stream`

职责：

- 触发 Agent 问答
- 返回同步回答或 SSE 流式回答

依赖：

- `chat_with_agent`
- `chat_with_agent_stream`

#### 文档接口

- `/documents`
- `/documents/upload`
- `DELETE /documents/{filename}`

职责：

- 管理员查看知识库文档
- 上传并入库文档
- 删除文档对应向量和父块

依赖：

- `DocumentLoader`
- `ParentChunkStore`
- `MilvusManager`
- `MilvusWriter`

风险点：

- 文件名直接用于 Milvus 过滤表达式，未做转义
- 文档列表实现是先查回最多 10000 条 chunk 再在应用层聚合，规模扩大后会变慢

## 3.3 鉴权层

### `backend/auth.py`

职责：

- 提供 DB Session 依赖
- 密码哈希与校验
- 生成 JWT
- 校验当前用户
- 管理员权限判断

密码策略：

- 新用户使用 PBKDF2-SHA256
- 历史密码兼容 bcrypt/passlib

JWT 载荷：

- `sub`
- `role`
- `exp`

优点：

- 密码存储比直接 bcrypt 兼容性更可控
- 管理员邀请码逻辑简单明了

局限：

- 无 refresh token
- 无 token 吊销
- 默认 `JWT_SECRET_KEY` 有硬编码兜底值 `change-this-secret`
- `OAuth2PasswordBearer(tokenUrl="/auth/login")` 与当前 JSON 登录接口形式不完全匹配，OpenAPI 体验可能不一致

## 3.4 数据库层

### `backend/database.py`

职责：

- 创建 SQLAlchemy `engine`
- 暴露 `SessionLocal`
- 暴露 `Base`
- 在启动时自动建表

实现特点：

- 默认 `DATABASE_URL` 是 `sqlite:///./supermew.db`
- 但 README 和 docker-compose 的主要目标依赖是 PostgreSQL

这说明项目同时支持：

- 轻量 SQLite 本地运行
- PostgreSQL 正式依赖

也带来一个实际风险：

- 当前仓库根目录和 `backend/` 下都存在 `supermew.db`，容易让开发者误判正在使用哪个库

### `backend/models.py`

定义了四张核心表：

1. `User`
- 用户名、密码哈希、角色、创建时间

2. `ChatSession`
- 用户会话
- 唯一键 `(user_id, session_id)`
- 存储 `metadata_json`

3. `ChatMessage`
- 消息正文
- 类型 `human/ai/system`
- 时间戳
- `rag_trace`

4. `ParentChunk`
- 文档父块
- 主键是 `chunk_id`
- 保存块层级、父子关系和文本

### `backend/schemas.py`

职责：

- 请求/响应模型定义
- `RagTrace` 契约定义

需要重点注意：

- `RagTrace.tool_name` 被定义为必填 `str`
- 但当前后端实际写入的 trace 并未稳定提供该字段

## 3.5 Agent 与会话层

### `backend/agent.py`

这是后端的核心聚合模块，承担两件事：

1. 会话消息持久化
2. LangChain Agent 运行与流式输出

### `ConversationStorage`

职责：

- 会话消息读写
- 会话列表查询
- Redis 缓存同步

存储位置：

- 关系库：`chat_sessions`、`chat_messages`
- 缓存：Redis 或内存字典

实现方式：

- `save()` 每次保存时会删除该会话所有旧消息，再把整段消息重新插入数据库
- `load()` 优先读缓存，未命中再回数据库

优点：

- 实现简单
- 数据模型容易理解

风险点：

- 每次回复都会全量重写消息，复杂度随会话长度增加
- 所有消息在一次保存中复用了同一个 `now` 时间，导致历史消息原始时间戳丢失

### `create_agent_instance()`

职责：

- 构造 LangChain Chat Model
- 构造工具型 Agent

已注册工具：

- `get_current_weather`
- `search_knowledge_base`
- `internet_crawler_search`

系统提示的目标：

- 能识别内部知识库问题
- 能查实时互联网信息
- 工具调用后必须给 Final Answer
- 同一轮不要重复调用相同工具

### `chat_with_agent()`

职责：

- 非流式调用
- 加载历史消息
- 摘要过长上下文
- 调用 Agent
- 回收最近一次 RAG trace
- 保存会话

### `chat_with_agent_stream()`

职责：

- SSE 流式调用
- 背景任务读取 Agent chunk
- 统一队列汇总正文与 RAG 步骤
- 支持前端主动中断
- 回写 `trace` 与消息持久化

这是当前系统最有价值的实现之一，因为它把同步工具执行阶段的“检索可视化”解决掉了。

## 3.6 工具层

### `backend/tools.py`

职责：

- 暴露给 Agent 的工具函数
- 保存最近一次 RAG trace
- 向流式队列发送检索步骤

包含：

1. `get_current_weather()`
- 调用高德天气接口

2. `search_knowledge_base()`
- 触发 `run_rag_graph()`
- 只允许每轮调用一次
- 把 `rag_trace` 缓存在 `_LAST_RAG_CONTEXT`

3. `internet_crawler_search()`
- 使用 `duckduckgo_search.DDGS`
- 只允许每轮调用一次

风险点：

- `duckduckgo_search` 没有在 `pyproject.toml` 声明
- `search_knowledge_base()` 返回的是“已经生成好的答案”，Agent 再次综合时属于“二次生成”模式
- trace 只保存了一部分字段，和前端展示预期并不完全一致

## 3.7 RAG 编排层

### `backend/rag_pipeline.py`

职责：

- 使用 LangGraph 编排 RAG 状态机
- 进行路由、检索、评分、重写、回答、幻觉检测

主要节点：

- `route_query_node`
- `decompose_query_node`
- `retrieve_initial`
- `grade_documents_node`
- `rewrite_question_node`
- `retrieve_expanded`
- `generate_answer_node`
- `grade_hallucination_node`

状态字段包括：

- `question`
- `queries`
- `context`
- `docs`
- `route`
- `intent`
- `expansion_type`
- `expanded_query`
- `step_back_question`
- `step_back_answer`
- `hypothetical_doc`
- `answer`
- `hallucination_score`
- `rag_trace`

优点：

- 链路完整
- 有可观测 trace
- 支持 Step-Back 与 HyDE
- 支持初检后质量门控和重写

风险点：

- `tool_name`、`initial_retrieved_chunks` 等 trace 字段没有完整写回
- chitchat / weather 路由逻辑在知识库工具内部存在概念重叠，职责边界不完全干净

### `backend/rag_utils.py`

职责：

- 检索实现
- Step-Back 和 HyDE 生成
- rerank 与 auto-merge

关键能力：

- `retrieve_documents()`
- `_rerank_documents()`
- `_auto_merge_documents()`
- `_merge_to_parent_level()`

值得特别注意：

- 查询时使用全局 `_embedding_service`
- 文档写入时使用 `MilvusWriter` 自己持有的 `EmbeddingService`
- BM25 状态没有稳定持久化，因此“写入时稀疏向量”和“查询时稀疏向量”可能不在同一词表体系

## 3.8 文档与向量层

### `backend/document_loader.py`

职责：

- 加载 PDF / Word / Excel
- 进行三级 token-based 分块

实现特点：

- 使用 `tiktoken`
- L1: 1000 tokens
- L2: 500 tokens
- L3: 250 tokens
- 保存层级关系 `chunk_id`、`parent_chunk_id`、`root_chunk_id`

### `backend/embedding.py`

职责：

- 调用外部 embedding API 生成 dense vector
- 自己实现一个简化版 BM25 稀疏向量

关键问题：

- `load_state()` / `save_state()` 使用 `json`，但文件顶部没有 `import json`
- `save_state()` 当前已实测会打印 `name 'json' is not defined`
- `save_state()` 在主链路中没有被调用，BM25 状态也没有稳定落盘

### `backend/milvus_writer.py`

职责：

- 对叶子块批量生成 dense/sparse embedding
- 写入 Milvus

实现特点：

- 只写 L3 叶子块
- 写入前对当前批次文本调用 `fit_corpus()`

风险点：

- 这里的 `fit_corpus()` 只基于当前上传文档批次，而不是整个知识库

### `backend/milvus_client.py`

职责：

- 封装 Milvus 客户端
- 管理 schema、index、查询、插入、删除
- 提供 hybrid retrieval 和 dense fallback

实际运行模式：

1. 真实 Milvus
- `MILVUS_URI` 以 `http` 开头时尝试连接

2. 本地 mock
- 否则直接进入 `AdvancedMockMilvusClient`
- 数据写入 `backend/mock_milvus_storage.json`
- dense 检索用 Numpy 计算余弦相似度
- hybrid 检索在 mock 下只是 dense surrogate

这意味着：

- 当前本地 mock 模式不能真实验证 sparse/hybrid 检索质量
- “dual mode” 主要验证的是系统可运行性，不是检索正确性等价

### `backend/parent_chunk_store.py`

职责：

- 持久化 L1/L2 父块
- 为 auto-merge 提供父块回查
- 读写 Redis 缓存

存储：

- 关系库表 `parent_chunks`
- 缓存 key 前缀 `parent_chunk:{chunk_id}`

## 3.9 后端模块间耦合与风险

最明显的耦合点：

1. import 级初始化
- `api.py`、`agent.py`、`rag_utils.py` 都在导入时创建长生命周期对象

2. 路径与导入耦合
- `backend/app.py` 依赖工作目录
- `main.py` 通过 `sys.path.append()` 修正

3. 共享全局状态
- `tools.py` 通过模块级变量维护 `_LAST_RAG_CONTEXT`
- 同时维护工具调用次数与 SSE 队列

4. 前后端 trace 契约耦合
- 前端模板与后端字段定义没有统一生成源

5. mock 模式与真实模式差异
- Redis/Milvus 的本地回退与线上行为并不等价

总体评价：

- 代码已经具备完整产品闭环
- 但工程边界、依赖注入、状态管理还停留在“可用但不够稳”的阶段
