# 10. 运行与排障

## 10.1 目标读者

这份 runbook 面向：

- 新接手项目的工程师
- 需要本地跑通环境的人
- 需要快速判断“当前跑的是不是 mock 模式”的人

## 10.2 先决条件

建议准备：

- Python 3.11 或 3.12
- 已安装依赖的虚拟环境
- Docker / Docker Compose

当前仓库内可见的本地习惯是：

- 使用 `.venv_311`
- `start.bat` 固定调用 `.venv_311\Scripts\python.exe`

## 10.3 环境变量

最少要准备：

- `ARK_API_KEY`
- `MODEL`
- `BASE_URL`
- `JWT_SECRET_KEY`
- `DATABASE_URL`

如果要启用完整链路，还需要：

- `EMBEDDER`
- `EMBEDDING_BASE_URL`
- `EMBEDDING_API_KEY`
- `MILVUS_URI` 或 `MILVUS_HOST`/`MILVUS_PORT`
- `REDIS_URL`

如果要启用可选能力，还需要：

- `RERANK_MODEL`
- `RERANK_BINDING_HOST`
- `RERANK_API_KEY`
- `AMAP_WEATHER_API`
- `AMAP_API_KEY`

## 10.4 基础设施启动

### Docker 启动

```bash
docker compose up -d
```

会启动：

- PostgreSQL
- Redis
- etcd
- MinIO
- Milvus standalone
- Attu

### 检查状态

```bash
docker compose ps
```

## 10.5 应用启动

### 当前最稳妥的方式

1. 根目录入口：

```bash
python main.py
```

2. 直接运行后端脚本：

```bash
python backend/app.py
```

3. Windows 脚本：

```bat
start.bat
```

### 当前不建议的方式

```bash
uvicorn backend.app:app --reload
```

原因：

- 当前 `backend/app.py` 使用裸导入
- 已实测 `import backend.app` 会失败

## 10.6 本地 smoke check

### 1. 双模运行检查

已验证过的命令：

```powershell
.\.venv_311\Scripts\python.exe tests/verify_dual_mode.py
```

可用于判断：

- Redis 是否进入 mock
- Milvus 是否进入 mock

本次验证结果：

- Redis 未连接成功，回退到内存缓存
- Milvus 处于本地 mock 模式

### 2. 文档切分检查

已验证过的命令：

```powershell
.\.venv_311\Scripts\python.exe tests/verify_token_loader.py
```

观察到的结果：

- `data/documents/test.pdf` 被成功切成 3 个 chunk
- 能看到 L1 和 L3 层级

说明：

- 命令输出完成后进程退出偏慢，本次工具层面记录为 timeout，但核心逻辑已经成功执行

### 3. 导入检查

用于验证标准 ASGI 导入是否可用：

```powershell
.\.venv_311\Scripts\python.exe -c "import backend.app"
```

本次结果：

- 失败，报 `ModuleNotFoundError: No module named 'api'`

### 4. BM25 状态持久化检查

用于验证 `EmbeddingService.save_state()`：

```powershell
.\.venv_311\Scripts\python.exe -c "from backend.embedding import EmbeddingService; svc=EmbeddingService(); svc.save_state()"
```

本次结果：

- 打印 `保存 BM25 状态失败: name 'json' is not defined`

## 10.7 常见故障

### 故障 1：`uvicorn backend.app:app` 无法启动

现象：

- `ModuleNotFoundError: No module named 'api'`

原因：

- `backend/app.py` 里是裸导入，不是包内导入

临时解决：

- 用 `python main.py` 或 `python backend/app.py`

根治方案：

- 参考 `09_improvements.md` 的 H1

### 故障 2：Redis 连不上

现象：

- 控制台打印“无法连接到 Redis，正在切换到本地内存缓存模式”

原因：

- `REDIS_URL` 不可达
- 本地没起 Redis

影响：

- 功能仍可用
- 但缓存只存在单进程内存

### 故障 3：Milvus 没连上

现象：

- 控制台打印进入本地 mock 模式

原因：

- `MILVUS_URI` 不是 HTTP 地址
- 或 Milvus 服务不可达

影响：

- 功能仍可跑
- 但 hybrid retrieval 质量验证失真

### 故障 4：联网搜索运行时报错

现象：

- 首次调用 `internet_crawler_search` 时出 import error

原因：

- `duckduckgo_search` 未在依赖中声明

临时解决：

- 手动安装该依赖

根治方案：

- 修复 `pyproject.toml`

### 故障 5：登录成功后又被踢回登录页

现象：

- 页面刷新后调用 `/auth/me` 返回 401

可能原因：

- JWT 过期
- `JWT_SECRET_KEY` 变化
- token 伪造/损坏

排查：

1. 检查 `JWT_EXPIRE_MINUTES`
2. 检查部署前后秘钥是否一致
3. 清理浏览器 `localStorage`

### 故障 6：文档上传很慢或超时

原因：

- 上传接口是同步做切分、embedding、入库
- 大文档会阻塞整个请求

临时建议：

- 先用小文档验证链路
- 检查模型 embedding 接口延迟

长期方案：

- 任务化

### 故障 7：知识库结果不稳定

可能原因：

- 当前跑在 Milvus mock 模式
- BM25 状态不一致
- rerank 未配置或不可达

排查建议：

1. 先确认当前是不是 mock 模式
2. 再确认 `RERANK_*` 配置
3. 最后检查文档是否确实已写入向量库

## 10.8 数据位置与清理

### 原始文档

- `data/documents/`

### SQLite

可能位置：

- `supermew.db`
- `backend/supermew.db`

### Milvus mock 数据

- `backend/mock_milvus_storage.json`

### 浏览器 token

- `localStorage.accessToken`

清理时需要注意：

- 删除向量并不会自动删除本地原始文件
- 会话删除只删当前用户对应会话
- 若当前在 SQLite 与 PostgreSQL 间切换，需先明确应用实际上连接的是哪一个

## 10.9 新成员接手建议

建议按这个顺序完成本地接手：

1. 看 `docs/01_overview.md`
2. 看 `docs/02_architecture.md`
3. 跑 `tests/verify_dual_mode.py`
4. 用 `python main.py` 启动应用
5. 完成注册/登录
6. 上传一个小 PDF
7. 用知识库问题验证 `/chat/stream`
8. 再读 `docs/09_improvements.md` 选择优先修复项

## 10.10 当前 runbook 的边界

这份 runbook 基于当前代码与当前机器上的实际核验整理。

未执行的内容：

- 未运行完整 pytest 套件
- 未验证真实 Milvus + Redis + PostgreSQL 全链路
- 未验证联网模型、rerank 服务和高德天气接口是否在当前环境可用

因此，凡是涉及外部网络服务的部分，都应在目标环境再次确认。
