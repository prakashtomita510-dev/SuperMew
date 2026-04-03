# 01. 项目概览

## 1.1 项目定位

SuperMew 当前是一个单体 Web 应用，包含：

- FastAPI 后端
- 纯静态前端页面，运行时由 FastAPI 直接挂载
- LangChain Agent
- 内置 RAG 检索链路
- 文档上传与向量化入库能力
- JWT 用户体系与 RBAC

它不是前后端分离部署架构，也不是微服务；更准确地说，它是“单进程 Web 应用 + 外部基础设施依赖”的形态。

核心业务目标：

- 面向登录用户提供聊天能力
- 面向管理员提供知识库文档管理能力
- 通过内部知识库检索、天气工具、联网搜索等工具扩展 Agent
- 将检索过程以可视化方式实时展示给前端

## 1.2 目录结构

运行时相关目录如下：

```text
SuperMew/
├─ backend/                  # FastAPI、Agent、RAG、鉴权、存储适配
├─ frontend/                 # 静态前端页面（HTML/CSS/JS + Vue CDN）
├─ data/
│  └─ documents/             # 上传后的原始文档落盘目录
├─ tests/                    # 验证脚本，偏 smoke/手工验证
├─ langchain-study/          # 学习/实验脚本，不属于主运行链路
├─ docker-compose.yml        # PostgreSQL / Redis / Milvus 相关依赖
├─ main.py                   # 根级启动入口
├─ start.bat                 # Windows 启动脚本
├─ pyproject.toml            # Python 依赖声明
└─ README.md                 # 项目说明
```

需要注意的非业务目录/文件：

- `.venv`、`.venv_311`：本地虚拟环境，不属于业务代码
- `supermew.db`、`backend/supermew.db`：SQLite 数据文件，说明当前仓库混有运行期数据
- `backend/mock_milvus_storage.json`：Milvus 回退模式下的本地 JSON 存储
- `backend/app_log.txt`、`backend/log.txt`：运行期日志副产物

## 1.3 模块划分

后端大致可以分为 6 层：

1. Web 层
- `backend/app.py`
- `backend/api.py`

2. 鉴权与用户层
- `backend/auth.py`
- `backend/models.py`
- `backend/schemas.py`
- `backend/database.py`

3. Agent 与会话层
- `backend/agent.py`
- `backend/cache.py`

4. RAG 编排层
- `backend/tools.py`
- `backend/rag_pipeline.py`
- `backend/rag_utils.py`

5. 文档处理与向量层
- `backend/document_loader.py`
- `backend/embedding.py`
- `backend/milvus_writer.py`
- `backend/milvus_client.py`
- `backend/parent_chunk_store.py`

6. 前端呈现层
- `frontend/index.html`
- `frontend/script.js`
- `frontend/style.css`

## 1.4 启动方式

### 推荐理解的真实入口

当前代码实际可工作的入口主要有两种：

1. `python main.py`
- `main.py` 会显式把 `backend/` 加入 `sys.path`
- 然后导入 `backend.app:app`
- 再用 `uvicorn.run()` 启动

2. `python backend/app.py`
- 因为脚本路径就是 `backend/`，内部的 `import api`、`from database import init_db` 能找到同目录模块

### Windows 脚本

`start.bat` 固定使用：

```bat
.venv_311\Scripts\python.exe backend/app.py
```

### 需要特别注意的一个事实

README 推荐的：

```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

在当前代码下会失败。已实际验证：

- `.\.venv_311\Scripts\python.exe -c "import backend.app"` 报错 `ModuleNotFoundError: No module named 'api'`

根因是 `backend/app.py` 使用了裸导入：

- `import api as api_module`
- `from database import init_db`

这使它依赖当前工作目录或 `sys.path` 被提前修改。

## 1.5 配置体系

### 环境变量

配置主要来自根目录 `.env`，代码通过 `os.getenv()` 读取。

主要分组如下：

- 模型配置：`ARK_API_KEY`、`MODEL`、`BASE_URL`、`GRADE_MODEL`
- Embedding 配置：`EMBEDDER`、`EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`
- Rerank 配置：`RERANK_MODEL`、`RERANK_BINDING_HOST`、`RERANK_API_KEY`
- 向量库配置：`MILVUS_HOST`、`MILVUS_PORT`、`MILVUS_COLLECTION`、`MILVUS_URI`
- 数据库/缓存：`DATABASE_URL`、`REDIS_URL`
- 鉴权：`JWT_SECRET_KEY`、`ADMIN_INVITE_CODE`、`JWT_ALGORITHM`、`JWT_EXPIRE_MINUTES`、`PASSWORD_PBKDF2_ROUNDS`
- 工具类：`AMAP_WEATHER_API`、`AMAP_API_KEY`
- 进程级：`HOST`、`PORT`
- 检索参数：`AUTO_MERGE_ENABLED`、`AUTO_MERGE_THRESHOLD`、`LEAF_RETRIEVE_LEVEL`

### Docker 配置

`docker-compose.yml` 只负责基础设施，不负责应用本身容器化：

- PostgreSQL
- Redis
- etcd
- MinIO
- Milvus standalone
- Attu

### 默认值与回退

代码内建了大量回退：

- 数据库默认回退到 SQLite：`sqlite:///./supermew.db`
- Redis 不可达时回退到内存字典
- Milvus 不可达时回退到本地 JSON + Numpy mock
- Rerank 未配置时直接跳过
- 稀疏混合检索失败时回退到 dense-only

这让项目在本地开发环境比较容易跑起来，但也让“当前到底跑在生产模式还是 mock 模式”变得不够显式。

## 1.6 当前运行形态总结

当前仓库更像是：

- 一个单体 FastAPI 应用
- 一个 CDN 驱动的静态前端
- 一个以 LangChain Agent 为核心、工具触发 RAG 的问答系统
- 一个以 Milvus/Redis/PostgreSQL 为目标依赖，同时允许本地 mock 降级的开发型实现

## 1.7 新成员应先掌握什么

建议优先理解下面 4 条主线：

1. FastAPI 如何挂载前端与 API
2. Agent 如何决定调用 `search_knowledge_base` 和 `internet_crawler_search`
3. 文档上传后如何分三级 chunk，并分别进入 PostgreSQL 与 Milvus
4. SSE 流式输出如何把“内容 chunk”和“RAG 步骤”同时推给前端
