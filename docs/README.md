# SuperMew 文档导航

本目录基于当前仓库代码事实整理，目标是帮助新成员完成理解、接手、排障与后续改造。

适合的阅读顺序：

1. `01_overview.md`
2. `02_architecture.md`
3. `03_backend.md`
4. `04_frontend.md`
5. `05_rag_pipeline.md`
6. `06_api.md`
7. `07_storage.md`
8. `08_diff_vs_upstream.md`
9. `09_improvements.md`
10. `10_runbook.md`

文档清单：

- `01_overview.md`：项目定位、目录、模块、启动方式、配置体系
- `02_architecture.md`：整体架构、核心数据流、Mermaid 图
- `03_backend.md`：后端模块逐个拆解
- `04_frontend.md`：前端结构、状态管理、接口调用、流式渲染
- `05_rag_pipeline.md`：文档入库与检索生成全链路
- `06_api.md`：接口说明、鉴权要求、SSE 事件格式
- `07_storage.md`：数据库、缓存、向量库、文件存储、环境变量
- `08_diff_vs_upstream.md`：相对上游的差异与影响
- `09_improvements.md`：按优先级排序的改进建议
- `10_runbook.md`：启动、验证、常见故障与排查

阅读提示：

- 结论优先来自代码，而不是根 README。
- 文档中的“上游差异”基于本地 `origin/main` 引用进行比较。当前离线环境下未重新 fetch，因此基线是本地缓存到的上游提交 `2f506d91`。
- 代码里存在部分运行期副产物和本地回退逻辑，文档中会明确区分“设计目标”和“当前实际行为”。
- 若文档里标注“推测/不确定”，表示代码没有充分证据，或行为依赖当前环境配置。

本次核验中实际执行过的只读验证：

- `.\.venv_311\Scripts\python.exe tests/verify_dual_mode.py`
- `.\.venv_311\Scripts\python.exe tests/verify_token_loader.py`
- `.\.venv_311\Scripts\python.exe -c "import backend.app"`
- `.\.venv_311\Scripts\python.exe -c "from backend.embedding import EmbeddingService; svc=EmbeddingService(); svc.save_state()"`

其中确认到的关键事实：

- 当前代码支持 Redis/Milvus 不可用时的本地回退模式。
- `DocumentLoader` 的三级分块在本地样本文档上可跑通。
- `uvicorn backend.app:app` 在当前实现下会失败，原因是 `backend/app.py` 使用了裸模块导入。
- `EmbeddingService.save_state()` 会打印 `name 'json' is not defined`，说明 BM25 状态持久化实现存在缺陷。
