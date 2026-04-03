# 09. 改进建议

本节按优先级列出问题。每条建议都包含：

- 问题描述
- 证据
- 影响
- 解决思路
- 实现难度
- 风险评估

## 9.1 高优先级

### H1. 修复包导入与启动方式不一致的问题

问题描述：

当前代码同时支持 `python main.py`、`python backend/app.py` 和 README 中宣称的 `uvicorn backend.app:app`，但这三种方式并不等价。实际代码依赖裸导入，导致标准 ASGI 导入方式会失败。

证据：

- `backend/app.py` 使用 `import api as api_module`、`from database import init_db`
- `main.py` 通过 `sys.path.append(...)` 强行修正导入路径
- README 多处推荐 `uvicorn backend.app:app`
- 实测 `.\.venv_311\Scripts\python.exe -c "import backend.app"` 失败，报 `ModuleNotFoundError: No module named 'api'`

影响：

- 部署方式不稳定
- 破坏标准 Python 包导入预期
- 增加测试、脚本、容器化时的踩坑概率

解决思路：

1. 把 `backend/` 变成标准包，补 `__init__.py`
2. 所有内部导入改为相对导入或包内绝对导入，例如 `from backend import api`
3. 统一只保留一种官方启动方式，例如 `uvicorn backend.app:app`
4. 更新 README 与脚本

实现难度：

- 中

风险评估：

- 中
- 会影响几乎所有导入路径，需要一轮完整回归

### H2. 修复 BM25 稀疏向量状态不一致与持久化缺陷

问题描述：

当前 sparse embedding 的状态管理不闭环。文档写入时会对当前批次 `fit_corpus()`，但查询时使用的是另一个全局 `EmbeddingService` 实例，且状态没有稳定保存。真实 Milvus hybrid 检索下，查询词表和入库词表可能不一致。

证据：

- `backend/milvus_writer.py` 在 `write_documents()` 中调用 `self.embedding_service.fit_corpus(all_texts)`
- `backend/rag_utils.py` 查询时使用全局 `_embedding_service.get_sparse_embedding(query)`
- `backend/embedding.py` 定义了 `save_state()` / `load_state()`，但主链路没有调用 `save_state()`
- `backend/embedding.py` 缺少 `import json`
- 实测 `EmbeddingService.save_state()` 打印 `name 'json' is not defined`

影响：

- hybrid retrieval 的 sparse 分量可能失真
- 本地 mock 模式下问题被掩盖，真实 Milvus 下才暴露
- 知识库规模增大后检索质量会不可预测

解决思路：

1. 明确 BM25 状态是“全库级”而不是“单批上传级”
2. 在文档增删后增量维护或重建全量 BM25 元数据
3. 写入后稳定保存元数据，并在查询端复用同一份状态
4. 修复 `json` 导入问题
5. 为 hybrid retrieval 增加真实回归测试

实现难度：

- 中到高

风险评估：

- 高
- 这是检索质量的基础层，修复不当会影响现有索引兼容性

### H3. 修复会话保存策略导致的全量重写和时间戳丢失

问题描述：

`ConversationStorage.save()` 当前每次保存会先删除整个会话的历史消息，再把全部消息重新插入数据库，并为这些消息写同一个 `now` 时间。

证据：

- `backend/agent.py` 中 `db.query(ChatMessage)...delete(...)`
- 紧接着按当前 `messages` 全量重新 `db.add(ChatMessage(... timestamp=now ...))`

影响：

- 历史消息原始时间戳被覆盖
- 会话越长，保存成本越高
- 增量审计和调试会变难

解决思路：

1. 改为 append-only 消息写入
2. 单独维护会话摘要和最后更新时间
3. 若需要重建摘要，只更新会话级字段，不重写消息表

实现难度：

- 中

风险评估：

- 中
- 需要兼容现有消息读取与删除逻辑

### H4. 补齐联网搜索依赖声明与故障策略

问题描述：

`internet_crawler_search()` 使用 `duckduckgo_search.DDGS`，但 `pyproject.toml` 中没有声明该依赖。

证据：

- `backend/tools.py` 中 `from duckduckgo_search import DDGS`
- `pyproject.toml` 依赖列表中未找到 `duckduckgo_search`

影响：

- 运行时会在首次调用联网搜索时失败
- 测试环境和生产环境之间容易出现“本地可用、部署不可用”

解决思路：

1. 在依赖中显式添加 `duckduckgo-search`
2. 若作为可选工具，放入 extras 并在未安装时返回可理解错误
3. 为 `internet_crawler_search()` 增加依赖缺失兜底信息

实现难度：

- 低

风险评估：

- 低

## 9.2 中优先级

### M1. 统一前后端 `ragTrace` 契约

问题描述：

前端模板期望 `tool_name`、`initial_retrieved_chunks` 等字段，但后端当前并未稳定产出这些字段。

证据：

- `backend/schemas.py` 里 `RagTrace` 定义了 `tool_name`、`initial_retrieved_chunks`
- `frontend/index.html` 显示这些字段
- `backend/rag_pipeline.py` 当前只稳定写了 `retrieved_chunks` 和 `expanded_retrieved_chunks`

影响：

- 前端界面出现空白字段
- 引用与检索过程说明不够可信
- 调试体验变差

解决思路：

1. 统一 trace 结构的“单一事实来源”
2. 后端明确填充 `tool_name`
3. 初检阶段单独写入 `initial_retrieved_chunks`
4. 前端对缺省字段做降级展示

实现难度：

- 低到中

风险评估：

- 低

### M2. 把 import-time 单例改为应用生命周期管理

问题描述：

多个模块在导入时直接初始化连接型对象或重型服务实例，导致测试、启动、配置切换和依赖替换都不够透明。

证据：

- `api.py` 模块级创建 `DocumentLoader`、`MilvusManager`、`EmbeddingService` 等
- `agent.py` 导入时创建 `agent, model = create_agent_instance()`
- `rag_utils.py` 导入时创建 `_embedding_service`、`_milvus_manager`、`_parent_chunk_store`

影响：

- 配置变更时不易热更新
- 测试难以注入 mock
- 导入动作就可能触发外部连接或环境绑定

解决思路：

1. 通过 FastAPI lifespan 或依赖注入统一创建服务
2. 把配置、连接、业务对象分层
3. 让测试可以显式传入 fake service

实现难度：

- 中

风险评估：

- 中

### M3. 调整鉴权接口与 OpenAPI/OAuth2 的契约

问题描述：

后端声明了 `OAuth2PasswordBearer(tokenUrl="/auth/login")`，但实际 `/auth/login` 接受的是 JSON 模型，而不是 OAuth2 Password Flow 常见的 form 数据。

证据：

- `backend/auth.py` 使用 `OAuth2PasswordBearer`
- `backend/api.py` 中 `/auth/login` 参数是 `LoginRequest`

影响：

- FastAPI 自带文档中的“Authorize”工作流不标准
- API 使用方容易误解认证方式

解决思路：

1. 如果想走 OAuth2 Password Flow，就改成 `OAuth2PasswordRequestForm`
2. 如果只想做 JWT 登录，就不要使用 `OAuth2PasswordBearer` 的这套叙事，改成更直接的 Bearer 认证说明

实现难度：

- 低到中

风险评估：

- 低

### M4. 收敛本地回退模式与真实生产模式的差异

问题描述：

当前本地回退模式虽然方便，但 Redis/Milvus mock 与真实服务差异较大，尤其 mock 下的 hybrid retrieval 并不真实。

证据：

- `cache.py` 回退到本地字典
- `milvus_client.py` 的 mock `hybrid_search()` 实际走 dense search surrogate
- `tests/verify_dual_mode.py` 主要验证的是“是否能运行”，不是检索一致性

影响：

- 开发阶段很难及早发现真实环境问题
- 让“demo 成功”掩盖“生产不等价”

解决思路：

1. 明确区分 `mock/dev/prod` 模式
2. 在 UI 或日志里显式打印当前模式
3. 对检索质量相关测试要求必须连接真实 Milvus

实现难度：

- 中

风险评估：

- 中

### M5. 调整文档列表与上传链路的同步阻塞设计

问题描述：

文档上传是同步请求，文档列表通过查询最多 10000 个 chunk 再应用层聚合获得。

证据：

- `backend/api.py` 的 `upload_document()` 完整执行切分、向量化、入库
- `list_documents()` 调用 `milvus_manager.query(... limit=10000)` 后再按文件名聚合

影响：

- 大文件上传时请求耗时长
- 文档数量增大后列表接口性能变差

解决思路：

1. 给文档建立元数据表
2. 上传改成后台任务
3. 前端查询任务状态和文档元数据，而不是扫 chunk

实现难度：

- 中到高

风险评估：

- 中

### M6. 收紧 CORS 与安全默认值

问题描述：

当前 CORS 设置过于宽泛，JWT 秘钥也存在不安全默认兜底。

证据：

- `backend/app.py`：`allow_origins=["*"]` 且 `allow_credentials=True`
- `backend/auth.py`：`JWT_SECRET_KEY` 默认 `change-this-secret`

影响：

- 部署时若遗漏环境变量，可能留下安全隐患
- CORS 语义不够清晰

解决思路：

1. 明确区分开发环境和生产环境的 CORS 配置
2. 在生产环境启动时强制要求配置安全秘钥
3. 启动时做配置校验

实现难度：

- 低

风险评估：

- 中

## 9.3 长期优化

### L1. 建立正式测试体系和 CI

问题描述：

当前 `tests/` 更多是验证脚本，缺少结构化单元测试、集成测试和 CI。

证据：

- `tests/verify_*.py` 命名与实现更像手工 smoke script
- 部分脚本依赖本地数据或外部模型

影响：

- 回归风险高
- 重构成本高

解决思路：

1. 按层拆出 unit / integration / e2e
2. 为 mock mode 和 real infra mode 各自建测试矩阵
3. 接入 CI

实现难度：

- 中到高

风险评估：

- 低

### L2. 增强可观测性

问题描述：

当前日志主要是 `print()` 和文本副产物，缺少结构化日志、指标和请求级追踪。

证据：

- 多处模块直接 `print(...)`
- 仓库中存在 `app_log.txt`、`log.txt` 这类副产物

影响：

- 出问题时难以定位
- 无法监控模型耗时、检索耗时、错误率

解决思路：

1. 统一 logging
2. 为聊天请求打 request id / session id
3. 加入关键指标：
- token 用量
- RAG 节点耗时
- 缓存命中率
- rerank 命中率

实现难度：

- 中

风险评估：

- 低

### L3. 文档入库任务化与进度可见化

问题描述：

当前上传接口是同步执行，缺少可恢复、可重试、可追踪的任务状态。

证据：

- `upload_document()` 直接串行完成所有工作

影响：

- 大文档体验差
- 超时风险高
- 用户难以理解“卡住在哪一步”

解决思路：

1. 引入任务队列
2. 文档任务状态表
3. 前端展示分阶段进度

实现难度：

- 高

风险评估：

- 中

### L4. 前端工程化与契约类型化

问题描述：

前端仍是单文件 + CDN 结构，随着能力变多会越来越难维护。

证据：

- `frontend/script.js` 集中维护全部状态和行为
- 契约没有类型校验

影响：

- 改动风险高
- 复杂交互难扩展

解决思路：

1. 迁移到正式 Vue 工程
2. 用 TypeScript 定义 API 和 `ragTrace`
3. 把聊天、历史、设置、引用弹窗拆成组件

实现难度：

- 中到高

风险评估：

- 中

### L5. 多租户文档权限与更细粒度 ACL

问题描述：

当前知识库是全局共享的，只有“管理员能管理、普通用户能使用”的粗粒度模型。

证据：

- 文档接口只做 `require_admin`
- 检索接口不区分用户可见文档集合

影响：

- 若进入多团队或多客户场景，隔离能力不足

解决思路：

1. 给文档增加 owner / tenant / visibility
2. 检索时增加过滤条件
3. 前端展示可访问的知识空间

实现难度：

- 高

风险评估：

- 中到高
