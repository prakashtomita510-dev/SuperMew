# 08. 与上游 SuperMew 的差异

## 8.1 比较基线说明

本节基于本地 Git 信息比较当前分支与上游引用：

- 当前分支：`main`
- 当前 HEAD：`eddca1a6`
- 本地上游基线：`origin/main` = `2f506d91`

说明：

- 当前环境离线，未重新 fetch GitHub
- 因此这里的“上游”是本地缓存到的 `origin/main`

## 8.2 提交级差异

当前分支比基线超前 3 个提交：

1. `592cb604`
- `Phase 2 Complete: Self-RAG (Hallucination Detection) implemented and verified`

2. `f0ce8ed9`
- `Phase 3 Complete: Citation Preview, Drag&Drop, Token-based Splitting`

3. `eddca1a6`
- `Phase6_Upgrade`

## 8.3 变更范围总览

相对上游，本地分支主要修改了：

- `backend/agent.py`
- `backend/cache.py`
- `backend/document_loader.py`
- `backend/embedding.py`
- `backend/milvus_client.py`
- `backend/rag_pipeline.py`
- `backend/tools.py`
- `frontend/index.html`
- `frontend/script.js`
- `frontend/style.css`
- `main.py`
- `pyproject.toml`
- `tests/*.py`

新增了：

- `tests/verify_agent_search.py`
- `tests/verify_dual_mode.py`
- `tests/verify_milvus_lite.py`
- `tests/verify_phase6.py`
- `tests/verify_search_tool.py`
- `tests/verify_self_rag.py`
- `tests/verify_token_loader.py`

以及若干运行期副产物：

- `backend/mock_milvus_storage.json`
- `backend/supermew.db`
- `backend/app_log.txt`
- `backend/log.txt`

## 8.4 主要新增能力

### 差异 1：Self-RAG / 幻觉检测链路

代码落点：

- `backend/rag_pipeline.py`

变化：

- 新增 `grade_hallucination_node`
- 生成回答后再做 groundedness 判断
- 不通过时可重试生成

收益：

- 回答质量控制更完整
- trace 信息更丰富

代价：

- 增加模型调用次数
- 让链路更长、更难调试

### 差异 2：更强的检索流程编排

代码落点：

- `backend/rag_pipeline.py`
- `backend/rag_utils.py`

变化：

- 路由器节点
- 多查询分解
- Step-Back / HyDE / complex 扩展
- 检索阶段 trace 强化

收益：

- 检索覆盖率更高
- 复杂问题比单轮向量检索更有机会召回到正确上下文

代价：

- 控制流更复杂
- 需要更多观测与测试

### 差异 3：前端引用预览与拖拽上传

代码落点：

- `frontend/index.html`
- `frontend/script.js`
- `frontend/style.css`

变化：

- `[1] [2]` 引用点击弹窗
- 管理员拖拽上传文档
- 更丰富的 RAG 过程呈现

收益：

- 用户更容易验证回答依据
- 文档管理体验更好

代价：

- 更依赖 `ragTrace` 契约完整性

### 差异 4：token-based 三级分块

代码落点：

- `backend/document_loader.py`

变化：

- 使用 `tiktoken`
- 改成 L1/L2/L3 分层分块

收益：

- 相比单层字符分块，层次信息更完整
- 为 auto-merge 提供结构基础

代价：

- 分块数量、层级关系、父子索引都更复杂

### 差异 5：dual-mode 回退增强

代码落点：

- `backend/cache.py`
- `backend/milvus_client.py`
- `main.py`

变化：

- Redis 不可用时回退到内存
- Milvus 不可用或非 HTTP URI 时回退到本地 mock
- 增加验证脚本辅助判断当前运行模式

收益：

- 本地开发阻力更小
- 基础设施缺失时仍可演示主流程

代价：

- “本地可跑”不等于“生产等价”
- 容易把 mock 结果误判为真实检索效果

## 8.5 架构层变化

相对上游，本地分支最明显的架构变化是：

1. RAG 控制流更像一个状态机
- 不再只是一次检索 + 生成

2. 前端变成强依赖 trace 的可视化客户端
- 展示的不只是回答，而是回答过程

3. 本地运行模式更偏“降级可用系统”
- 通过 mock 保证基本闭环

## 8.6 行为层变化

### 聊天行为

- 更倾向先分解查询再检索
- 检索结果会经过评分、重写和幻觉检测

### 文档处理行为

- 切块方式从更简单形式演进到三级 token-based 分块

### 前端交互行为

- 增强引用交互
- 新增拖拽上传
- 展示 RAG 过程细节

## 8.7 收益与代价总结

### 收益

- 回答链路更完整
- 用户体验更丰富
- 开发环境更容易起步
- 可解释性明显增强

### 代价

- 工程复杂度上升
- trace 契约、状态同步、mock 一致性问题更突出
- 回归测试需求更高

## 8.8 当前差异分析的边界

以下结论是确定的：

- 当前分支比本地 `origin/main` 多 3 个提交
- 上述能力主要由这 3 个提交引入

以下结论需要谨慎理解：

- 若 GitHub 上游仓库在本地最后 fetch 之后又有新提交，本节不会体现
- 因为没有在线拉取上游最新代码，所以这里只能说明“相对本地上游引用”的差异
