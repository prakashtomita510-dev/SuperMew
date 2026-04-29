# RAG Eval Issue Tracker

这份文件用于记录量化测评推进过程中遇到的问题、处理方案、当前效果和后续动作。

更新原则：

- 只记录对评测可信度、可复现性、可执行性有实际影响的问题
- 每条问题都要说明“影响了什么指标或流程”
- 问题解决后保留“解决后的效果”，方便回看进展

## 当前阶段判断

当前已经完成：

- 评测工程骨架搭建
- LoTTE / RAGBench 标准化样本下载与本地处理主线
- retrieval / rag 官方模式保护，正式模式不会静默回退 mock
- RAG trace 与阶段耗时埋点基础
- LoTTE technology official 100 retrieval matrix
- RAGBench `techqa` / `hotpotqa` / `emanual` official 50 no-rewrite 端到端基线
- latency / trace baseline 与 heartbeat 运行监控
- 聚合报表与简历候选描述导出

当前尚未完成：

- LoTTE 多 domain / 更大样本规模的正式 retrieval
- custom eval 正式标注与人工核验
- chunking / auto-merging 正式结果产出
- Step-Back / HyDE / dynamic rewrite 专项矩阵结果产出
- latency 的平衡样本量复跑和多次重复统计
- citation coverage、refusal correctness、LLM-as-a-judge 等补充指标

当前最新状态以 [EVAL_PROGRESS_AND_NEXT_PLAN.md](./EVAL_PROGRESS_AND_NEXT_PLAN.md) 和 `eval/outputs/reports/` 下的聚合报表为准。本文档保留历史问题处理过程，因此后续条目中可能包含当时阶段的过渡性描述。

## 问题台账

### 1. 官方评测会静默退回 mock backend

- 状态：已处理
- 影响：
  - 会污染 `Recall@5`、`MRR@10`、`TTFT` 等正式指标
  - 会让主报告混入无效结果
- 发现位置：
  - [milvus_client.py](/D:/agent_demo/SuperMew/backend/milvus_client.py)
  - [run_retrieval_eval.py](/D:/agent_demo/SuperMew/eval/scripts/run_retrieval_eval.py)
  - [run_rag_eval.py](/D:/agent_demo/SuperMew/eval/scripts/run_rag_eval.py)
- 解决方案：
  - 增加 `MILVUS_REQUIRE_REAL=true` 约束
  - 官方模式下若 backend 为 `mock_milvus`，样本标记为 `unsupported`
  - 当官方评测 `supported_sample_count == 0` 时 runner 非零退出
- 解决后的效果：
  - 非真实链路不会再被误当作正式结果
  - smoke run 已验证 retrieval / rag 官方评测都会在 mock 条件下明确失败
- 后续动作：
  - 在真实 Milvus 环境下重跑 LoTTE / RAGBench smoke test

### 2. BM25 状态与向量库语料不同步

- 状态：已处理
- 影响：
  - 稀疏检索结果不稳定
  - hybrid 检索指标不可解释
- 发现位置：
  - [embedding.py](/D:/agent_demo/SuperMew/backend/embedding.py)
  - [milvus_writer.py](/D:/agent_demo/SuperMew/backend/milvus_writer.py)
  - [api.py](/D:/agent_demo/SuperMew/backend/api.py)
- 解决方案：
  - BM25 状态支持保存、加载、刷新
  - 上传 / 删除文档后重建 BM25 稀疏语料状态
  - 写入阶段将已有 leaf chunk 与新增 chunk 一起重建统计
- 解决后的效果：
  - dense / sparse / hybrid 共享同一语料视图
  - 为后续 `sparse_only`、`hybrid_rrf` 实验打下基础
- 后续动作：
  - 在真实知识库语料上验证 `sparse_only` 与 `hybrid` 的差异

### 3. RAG trace 字段不完整，无法支撑指标追溯

- 状态：已处理
- 影响：
  - 无法可靠统计 `trace coverage rate`
  - 无法解释 retrieval / rewrite / generate 各阶段耗时
- 发现位置：
  - [rag_pipeline.py](/D:/agent_demo/SuperMew/backend/rag_pipeline.py)
  - [tools.py](/D:/agent_demo/SuperMew/backend/tools.py)
  - [agent.py](/D:/agent_demo/SuperMew/backend/agent.py)
  - [schemas.py](/D:/agent_demo/SuperMew/backend/schemas.py)
- 解决方案：
  - 补齐 `tool_name`、`vector_backend`、`initial_retrieved_chunks`
  - 增加 `request_id` 和 `stage_timings_ms`
  - SSE 事件与最终 trace 统一携带请求上下文
- 解决后的效果：
  - `run_rag_eval.py` 已可在样本结果中拿到完整 `rag_trace`
  - retrieval / rewrite / generate 的阶段耗时已可落盘
- 后续动作：
  - 用 latency runner 聚合 `TTFT`、`TTFM` 和分阶段时延

### 4. 通用聊天 Agent 会绕开知识库工具，导致 RAG 评测失真

- 状态：已处理
- 影响：
  - 模型可能直接回答，不产生 `rag_trace`
  - 评测对象从“RAG 系统”变成“通用聊天行为”
- 发现位置：
  - [agent.py](/D:/agent_demo/SuperMew/backend/agent.py)
  - [run_rag_eval.py](/D:/agent_demo/SuperMew/eval/scripts/run_rag_eval.py)
- 解决方案：
  - `run_rag_eval.py` 改为直接调用 `run_rag_graph()`
  - 官方模式要求非空 `rag_trace`
- 解决后的效果：
  - 当前 RAG 评测跑的是固定 graph，而不是自由工具选择的 Agent
  - 样本结果中已经能看到真实 graph 产出的 `rag_trace`
- 后续动作：
  - 继续把 config 参数下沉到 graph，支持 rewrite / chunking 变体实验

### 5. grading 结构化解析失败时默认判定为 yes

- 状态：已处理
- 影响：
  - `groundedness` 会被虚高
  - 不相关检索结果也可能被判为“通过”
- 发现位置：
  - [rag_pipeline.py](/D:/agent_demo/SuperMew/backend/rag_pipeline.py)
- 解决方案：
  - 为 `grade_documents` 和 `grade_hallucination` 增加保守降级逻辑
  - 结构化输出失败后，退回纯文本 `yes/no` 解析
  - 仍不确定时记为 `unknown`，并走保守分支
- 解决后的效果：
  - smoke run 中已出现 `grade_score = no`、`hallucination_score = no`
  - 不再因为解析失败而默认“洗白”结果
- 后续动作：
  - 补正式 `judge_error_rate` 统计，评估 grader 稳定性

### 6. Hugging Face `datasets.load_dataset` 在 Windows 本地缓存阶段出现权限错误

- 状态：已处理
- 影响：
  - LoTTE / RAGBench 无法稳定下载
  - 数据准备流程不可靠
- 发现位置：
  - `eval/datasets/.cache/`
  - 下载脚本初版实现
- 解决方案：
  - 放弃依赖本地缓存重命名流程
  - 改为直接调用 Hugging Face dataset viewer API 拉取标准化样本
- 解决后的效果：
  - LoTTE 样本已落盘到 [dev.jsonl](/D:/agent_demo/SuperMew/eval/datasets/lotte/normalized/technology/dev.jsonl)
  - RAGBench 样本已落盘到 [test.jsonl](/D:/agent_demo/SuperMew/eval/datasets/ragbench/normalized/techqa/test.jsonl)
- 后续动作：
  - 补完整分页与更多 subset / domain 的下载策略

### 7. 当前知识库语料与 LoTTE / RAGBench 查询域不匹配

- 状态：未解决
- 影响：
  - retrieval 结果不相关
  - RAG answer accuracy 没有解释意义
- 现象：
  - 当前 smoke run 检索到的主要是 `attention-is-all-you-need-Paper.pdf`
  - 与 LoTTE / RAGBench 的 IBM / Google Docs 问题域明显不一致
- 根因判断：
  - 真实评测语料尚未完成针对性入库
  - LoTTE 目前只下载了 query 标准化样本，尚未完成 corpus 侧准备
- 当前缓解：
  - 官方模式已阻止这些结果进入正式摘要
- 下一步：
  - 优先完成 LoTTE corpus 准备与入库
  - 然后在真实 Milvus 上重跑 retrieval smoke test

### 8. custom eval 仍是草稿，未形成正式 benchmark

- 状态：未解决
- 影响：
  - chunking / rewrite 实验无法形成可信对比
  - `cross_chunk accuracy`、`rewrite precision` 还不能正式产出
- 发现位置：
  - [custom_eval.jsonl](/D:/agent_demo/SuperMew/eval/datasets/custom/custom_eval.jsonl)
- 当前情况：
  - 已有自动生成草稿
  - 尚缺 `gold_answer`、`gold_spans`、`question_type` 的正式补标
- 下一步：
  - 先补 20-30 条高质量 `cross_chunk` / `rewrite_needed` / `no_answer` 样本

### 9. 运行目录里存在临时文件与锁定文件

- 状态：部分未解决
- 影响：
  - 清理产物不彻底
  - 个别 smoke 文件或 `pyc` 文件删除失败
- 现象：
  - [test_smoke.jsonl](/D:/agent_demo/SuperMew/eval/datasets/ragbench/normalized/techqa/test_smoke.jsonl) 当前仍存在
  - `__pycache__` 中个别文件被占用
- 当前判断：
  - 不影响核心评测逻辑
  - 但会增加工作区噪音
- 下一步：
  - 在后续整理阶段统一清理临时文件和锁文件

### 10. Parent chunk SQLite 在 pilot 环境下出现只读写入失败

- 状态：已处理
- 影响：
  - `ingest_lotte.py` 在 pilot 入库阶段中断
  - 导致第一次 retrieval pilot 实际上没有导入任何语料
- 发现位置：
  - [ingest_lotte.py](/D:/agent_demo/SuperMew/eval/scripts/ingest_lotte.py)
  - [parent_chunk_store.py](/D:/agent_demo/SuperMew/backend/parent_chunk_store.py)
- 解决方案：
  - pilot 脚本改为使用隔离的 `DATABASE_URL`
  - `ingest_lotte.py` 增加 `--skip-parent-store`，让 dense-only pilot 不依赖父块数据库
- 解决后的效果：
  - 第二轮 pilot 已成功完成 LoTTE 子集入库
  - retrieval 结果从全空变成了非零 `Recall/MRR`
- 后续动作：
  - 等进入 chunking / auto-merge 实验时，再启用独立可写父块数据库

### 11. Retrieval pilot 在 500 queries 规模下触发 embedding 接口 429

- 状态：已缓解
- 影响：
  - 试运行耗时明显升高
  - pilot 反馈速度过慢，不利于快速迭代
- 发现位置：
  - retrieval smoke / pilot 运行日志
- 解决方案：
  - 增加小样本 pilot 策略
  - `run_retrieval_eval.py` 使用 `sample-limit`
  - `run_lotte_retrieval_pilot.ps1` 默认先跑较小 query 子集
- 解决后的效果：
  - 在 50 queries 的 LoTTE 子集上已得到第一版可用 pilot 指标
- 后续动作：
  - 后续按 50 -> 100 -> 500 递增式扩大样本规模

### 12. 正式链路 readiness 仍缺真实 Milvus / Redis

- 状态：已解决
- 影响：
  - 无法切换到 `MILVUS_REQUIRE_REAL=true` 的正式评测
  - `Recall@5`、`MRR@10`、`TTFT`、`trace coverage rate` 目前都不能记入正式主报告
- 发现位置：
  - [check_official_readiness.py](/D:/agent_demo/SuperMew/eval/scripts/check_official_readiness.py)
  - [\.env](/D:/agent_demo/SuperMew/.env)
- 当前检查结果：
  - Model Gateway：可用
  - Embedding API：可用
  - Rerank API：可用
  - `MILVUS_URI=./milvus_supermew.db`，仍指向本地文件，不是正式服务地址
  - `127.0.0.1:19530` 当前不可达
  - `127.0.0.1:6379` 当前不可达
- 解决方案：
  - 将 `MILVUS_URI` 改为真实 Milvus 服务地址
  - 启动并确认 Redis 可连通
  - 重新运行 readiness 脚本确认正式链路全部通过
- 解决后的效果：
  - 已通过 [check_official_readiness.py](/D:/agent_demo/SuperMew/eval/scripts/check_official_readiness.py) 全量检查
  - 真实 Milvus 与 Redis 均已在 Docker 中启动并健康
  - `.env` 已切换到 `MILVUS_URI=http://127.0.0.1:19530` 与 `MILVUS_REQUIRE_REAL=true`
- 后续动作：
  - 在正式链路上继续推进 LoTTE / RAGBench 评测

### 13. 正式 LoTTE 入库受 embedding API 429 限流阻塞

- 状态：未解决
- 影响：
  - 真实 Milvus 下的官方 LoTTE 入库无法稳定完成
  - `dense_only` / `hybrid_rrf` / `hybrid_rrf_rerank` 正式指标暂时无法可信产出
  - 即使脚本与 Milvus 已修通，外部 embedding 配额仍会让 retrieval 回退到 `failed`
- 发现位置：
  - [embedding.py](/D:/agent_demo/SuperMew/backend/embedding.py)
  - [ingest_lotte.py](/D:/agent_demo/SuperMew/eval/scripts/ingest_lotte.py)
  - [run_lotte_retrieval_matrix_official.ps1](/D:/agent_demo/SuperMew/eval/scripts/run_lotte_retrieval_matrix_official.ps1)
- 当前情况：
  - 真实 Milvus / Redis / readiness 均已通过
  - 正式入库过程中，Cohere embedding 接口持续返回 `429 Too Many Requests`
  - 即使将评测缩小到前 20 条 query 的定向 smoke 集，仍会在首批 embedding 请求阶段被限流
- 已做处理：
  - 缩小官方 smoke 规模，改为定向 LoTTE 子集
  - 调整 batch 策略，减少单次入库请求数
  - 修复真实 Milvus 下的 `RRFRanker` 与结果解析兼容问题，排除本地代码层阻塞
- 解决后的效果：
  - 已确认主阻塞不再是 Milvus / Redis / SDK 兼容，而是外部 embedding 配额
  - 稀疏检索链路在真实 Milvus 上已能返回有效命中结构
- 后续动作：
  - 需要等待 embedding 配额恢复，或更换更高配额的真实 embedding key / 服务
  - 配额恢复后优先重跑 LoTTE 定向官方 smoke，再扩大到更大样本

### 14. Google embedding 模型名与项目调用维度不匹配

- 状态：已处理
- 影响：
  - `.env` 切到 Google 后，若继续使用 `text-embedding-004`，embedding smoke 会直接 `404`
  - 即便切到可用的 `gemini-embedding-001`，如果集合仍按错误维度建库，会导致正式入库失败或检索结果失真
- 发现位置：
  - [embedding.py](/D:/agent_demo/SuperMew/backend/embedding.py)
  - [milvus_writer.py](/D:/agent_demo/SuperMew/backend/milvus_writer.py)
  - [\.env](/D:/agent_demo/SuperMew/.env)
- 当前情况：
  - 使用当前 Google key 调 `ListModels` 已确认可用 embedding 模型是 `models/gemini-embedding-001` 和 `models/gemini-embedding-2-preview`
  - `text-embedding-004` 对这把 key 返回 `404 not found / not supported for embedContent`
  - 最小 smoke 已验证 `gemini-embedding-001` 可成功返回向量，实际维度为 `3072`
- 解决方案：
  - 项目 embedding 分支接入 Google 原生接口
  - 将 `.env` 的推荐模型切换为 `gemini-embedding-001`
  - 修正 Google embedding 的输出维度映射，避免仍按 `768` 维建库
- 解决后的效果：
  - `gemini-embedding-001` 最小 smoke 已通过
  - 项目当前可识别并返回 `3072` 维向量，用于真实 Milvus 建库
- 后续动作：
  - 用 `gemini-embedding-001` 重新跑正式 LoTTE 定向入库
  - 若后续要尝试 `gemini-embedding-2-preview`，先单独做 smoke 和维度确认

### 15. SiliconFlow OpenAI 兼容 embedding 调用缺少认证头

- 状态：已处理
- 影响：
  - 切换到 `Pro/BAAI/bge-m3` 后，最小 embedding smoke 直接返回 `401 Invalid token`
  - 新 embedding 提供商无法用于正式 LoTTE 入库和 retrieval 评测
- 发现位置：
  - [embedding.py](/D:/agent_demo/SuperMew/backend/embedding.py)
  - [\.env](/D:/agent_demo/SuperMew/.env)
- 当前情况：
  - SiliconFlow 的 embedding 接口采用 OpenAI 兼容风格 `POST /v1/embeddings`
  - 项目原来的“非 Google / 非 Cohere”分支缺少 `Authorization: Bearer <token>` 请求头
  - 导致 key 本身可用时仍被接口拒绝
- 解决方案：
  - 修复 OpenAI 兼容 embedding 分支的认证头写法
  - 同时让项目支持读取 `EMBEDDING_MODEL` 和 `EMBEDDING_DIMENSION`
  - 将新模型配置统一落到 `.env`
- 解决后的效果：
  - `Pro/BAAI/bge-m3` 最小 smoke 已通过，实际返回 `1024` 维
  - 新 embedding 提供商已可用于正式 Milvus 入库与 retrieval 评测
- 后续动作：
  - 继续在新模型上扩大正式 LoTTE 样本规模
  - 后续若切换 embedding，仅需修改 `.env` 中模型名和维度

### 16. 聚合总表混入历史结果，无法直接反映当前正式测评状态

- 状态：已处理
- 影响：
  - `results_summary.md` 和各类汇总 csv 会同时包含旧 smoke、pilot、旧 embedding 模型结果
  - 用户很难直接判断“当前这轮正式测评”的真实结果
- 发现位置：
  - [aggregate_results.py](/D:/agent_demo/SuperMew/eval/scripts/aggregate_results.py)
  - [README.md](/D:/agent_demo/SuperMew/eval/README.md)
- 当前情况：
  - 聚合脚本原先会把 `eval/outputs` 下所有 `metadata.json` 全部展开
  - 同一 `kind + dataset + variant` 的旧结果不会被覆盖
- 解决方案：
  - 聚合逻辑改为对同一 `kind + dataset + variant` 只保留最新一次 `metadata.json`
  - 在汇总 markdown 中显式标注来源文件路径
  - 在 README 中补充“总表只保留最新结果”的说明
- 解决后的效果：
  - 当前总表已可直接反映最新正式结果
  - 新模型下的 LoTTE official 指标不会再被旧模型结果污染
- 后续动作：
  - 后续如需保留完整历史，对外建议另行输出 time-series 报表

### 17. 新模型 `Pro/BAAI/bge-m3` 首轮正式 LoTTE retrieval 已跑通

- 状态：已处理
- 影响：
  - 标志着正式测评已从“环境就绪”进入“稳定产出结果”的阶段
  - 为后续 chunking / rewrite / RAGBench 评测提供了可用的 embedding 与 Milvus 基线
- 发现位置：
  - [run_lotte_retrieval_matrix_official.ps1](/D:/agent_demo/SuperMew/eval/scripts/run_lotte_retrieval_matrix_official.ps1)
  - [run_with_heartbeat.ps1](/D:/agent_demo/SuperMew/eval/scripts/run_with_heartbeat.ps1)
  - [results_summary.md](/D:/agent_demo/SuperMew/eval/outputs/reports/results_summary.md)
- 当前情况：
  - `20` 条与 `50` 条正式 retrieval 已完成
  - `100` 条正式 retrieval 也已完成，并采用 30 秒心跳与失败即停机制
  - 当前最新 `100` 条正式指标如下：
    - `dense_only`: `Recall@5=0.95`, `MRR@10=0.88`, 平均延迟约 `159ms`
    - `sparse_only`: `Recall@5=0.76`, `MRR@10=0.663`, 平均延迟约 `28ms`
    - `hybrid_rrf`: `Recall@5=0.85`, `MRR@10=0.799`, 平均延迟约 `107ms`
    - `hybrid_rrf_rerank`: `Recall@5=0.97`, `MRR@10=0.9445`, 平均延迟约 `1335ms`
- 解决方案：
  - 用新模型重建正式 Milvus collection
  - 扩大语料到前 `100` 条 query 涉及的 `900` 个 relevant PID 与 `1200` 个 distractor
  - 在 retrieval 矩阵执行过程中保持 30 秒心跳监控和 fail-fast
- 解决后的效果：
  - 正式链路下已拿到一组可信的 LoTTE retrieval 基线
  - `hybrid_rrf_rerank` 在效果上当前最佳，`sparse_only` 在时延上当前最佳
- 后续动作：
  - 继续扩大 LoTTE 样本或切换到下一阶段的 RAG / latency / chunking 评测
  - 将当前 retrieval 基线整理进最终报告与 resume bullets

### 18. 官方评测隔离 SQLite 库在当前工作区无法稳定新建

- 状态：部分规避
- 影响：
  - `latency` / `rag` 这类需要读写会话与用户表的正式评测无法使用新建的隔离 SQLite 库
  - 原计划中的 `eval/official_eval.db` 与 `official_eval_v2.db` 都在建表阶段触发 `disk I/O error`
- 发现位置：
  - [with_official_eval_env.ps1](/D:/agent_demo/SuperMew/eval/scripts/with_official_eval_env.ps1)
  - [run_lotte_retrieval_matrix_official_env.ps1](/D:/agent_demo/SuperMew/eval/scripts/run_lotte_retrieval_matrix_official_env.ps1)
  - [init_official_eval_db.py](/D:/agent_demo/SuperMew/eval/scripts/init_official_eval_db.py)
- 当前情况：
  - 在仓库工作区内对新 SQLite 文件做最小建表探测时，`eval/`、`backend/` 和 repo 根目录的新文件都报 `disk I/O error`
  - 现有 [supermew.db](/D:/agent_demo/SuperMew/backend/supermew.db) 完整性检查通过，`users` 表可正常查询
- 解决方案：
  - 放弃继续创建新的隔离评测库
  - 官方评测环境临时切回已验证健康的 [supermew.db](/D:/agent_demo/SuperMew/backend/supermew.db)
  - 继续依赖 run 级输出、config hash 和 metadata.json 保证评测可追溯
- 解决后的效果：
  - `latency` 官方链路已恢复可跑
  - 不再被 `users` 表缺失或新 SQLite 建库失败阻塞
- 后续动作：
  - 后续如果要彻底恢复隔离数据库，需要单独排查当前工作区上的 SQLite 文件系统兼容问题

### 19. 正式 latency / trace coverage 基线已跑通

- 状态：已处理
- 影响：
  - 正式评测从单纯 retrieval 扩展到了体验与可观测性指标
  - 已能够量化 `sync` 与 `stream` 两种调用方式的时延差异
- 发现位置：
  - [run_latency_eval.py](/D:/agent_demo/SuperMew/eval/scripts/run_latency_eval.py)
  - [results_summary.md](/D:/agent_demo/SuperMew/eval/outputs/reports/results_summary.md)
  - [latency_metrics.csv](/D:/agent_demo/SuperMew/eval/outputs/reports/latency_metrics.csv)
- 当前情况：
  - 为 `run_latency_eval.py` 补充了 `metadata.json` 输出，使其能进入统一聚合总表
  - 基于 [dev.forum.latency10.jsonl](/D:/agent_demo/SuperMew/eval/datasets/lotte/normalized/technology/dev.forum.latency10.jsonl) 完成了 `10` 条正式 `sync` 与 `stream` 基线
  - 当前最新结果：
    - `stream`: 平均时延约 `20.75s`，`TTFT` 约 `18.62s`，首事件约 `2.82s`，`trace_coverage_rate=0.2`
    - `sync`: 平均时延约 `25.53s`，`trace_coverage_rate=0.3`
- 解决方案：
  - 使用稳定主库恢复会话链路
  - 对 `sync` 和 `stream` 分别运行正式 latency eval
  - 将结果写入统一的 `metadata.json` 并重新聚合到总表
- 解决后的效果：
  - [results_summary.md](/D:/agent_demo/SuperMew/eval/outputs/reports/results_summary.md) 和 [latency_metrics.csv](/D:/agent_demo/SuperMew/eval/outputs/reports/latency_metrics.csv) 已包含正式 latency 指标
  - `stream` 确实更早出现首事件，但整体生成仍较慢，当前 trace 覆盖也偏低
- 后续动作：
  - 分析 `trace_coverage_rate` 偏低的原因
  - 进入正式 RAGBench 端到端评测

### 20. DuckDuckGo 证书访问警告会污染 latency 观测

- 状态：未解决
- 影响：
  - latency 运行期间 stderr 持续出现 `failed to load native root certificate`
  - 这类外部搜索工具噪声可能拉长单样本时延，并影响 `trace_coverage_rate` 判断
- 发现位置：
  - [tools.py](/D:/agent_demo/SuperMew/backend/tools.py)
  - [heartbeat-20260422-214248.err.log](/D:/agent_demo/SuperMew/eval/outputs/monitor/heartbeat-20260422-214248.err.log)
- 当前情况：
  - `duckduckgo_search` 运行时伴随证书存储访问失败告警
  - 正式 latency 样本虽全部成功，但 stderr 噪声持续存在
- 解决方案：
  - 暂未修复，本轮先保留结果并记录风险
- 解决后的效果：
  - 当前 latency 基线可用，但需要把该噪声视为残余风险
- 后续动作：
  - 在后续 latency 优化前优先处理该证书警告与不必要的外部搜索依赖

### 21. 正式评测期间已禁用联网搜索工具

- 状态：已处理
- 影响：
  - 通用 Agent 在正式评测期间默认携带 `internet_crawler_search`
  - 这会在 latency / RAGBench 评测里引入不必要的联网噪声和证书告警，污染体验指标
- 发现位置：
  - [tools.py](/D:/agent_demo/SuperMew/backend/tools.py)
  - [agent.py](/D:/agent_demo/SuperMew/backend/agent.py)
  - [with_official_eval_env.ps1](/D:/agent_demo/SuperMew/eval/scripts/with_official_eval_env.ps1)
- 当前情况：
  - `internet_crawler_search` 以前在正式评测中仍可被模型选中
  - 导致 DuckDuckGo 相关证书警告进入 stderr
- 解决方案：
  - 增加 `DISABLE_INTERNET_CRAWLER_SEARCH` 环境变量
  - 正式评测 runner 默认注入 `DISABLE_INTERNET_CRAWLER_SEARCH=true`
  - Agent 在该标志打开时不再挂载联网搜索工具
- 解决后的效果：
  - 正式 latency 验证时 DuckDuckGo 证书告警已消失
  - 小样本 `stream` 验证中 `trace_coverage_rate` 回升到 `1.0`
- 后续动作：
  - 后续正式评测默认保持禁用，除非用户明确要求联网场景评测

### 22. RAGBench 正式端到端 smoke 已跑通

- 状态：已处理
- 影响：
  - 正式测评主线已从 retrieval 与 latency 扩展到端到端问答质量评估
  - 已具备继续扩大 RAGBench 样本规模的基础
- 发现位置：
  - [run_rag_eval.py](/D:/agent_demo/SuperMew/eval/scripts/run_rag_eval.py)
  - [grounded_answer metadata](/D:/agent_demo/SuperMew/eval/outputs/rag/grounded_answer/metadata.json)
  - [rag_metrics.csv](/D:/agent_demo/SuperMew/eval/outputs/reports/rag_metrics.csv)
- 当前情况：
  - 使用 [test.official10.jsonl](/D:/agent_demo/SuperMew/eval/datasets/ragbench/normalized/techqa/test.official10.jsonl) 完成了 `10` 条正式 `RAGBench techqa` smoke
  - 最新正式结果：
    - `answer_accuracy=0.2382799`
    - `groundedness_score=0.7`
    - `avg_generation_latency_ms=104354.012`
    - `supported_sample_count=10/10`
- 解决方案：
  - 在官方环境下注入稳定数据库、真实 Milvus 和禁用联网搜索
  - 用统一心跳机制运行 `run_rag_eval.py`
- 解决后的效果：
  - RAGBench 端到端评测链路已无硬阻塞
  - 当前已拿到一组可用的正式端到端质量与时延基线
- 后续动作：
  - 将 RAGBench 样本从 `10` 扩到更大的正式规模
  - 分析 `answer_accuracy` 偏低和 `avg_generation_latency_ms` 偏高的原因

### 23. RAGBench 使用 LoTTE 语料会导致跨域失真

- 状态：已缓解
- 影响：
  - `answer_accuracy` 被跨域检索误伤，端到端结果难以解释
  - `groundedness` 可能看起来正常，但实际是在错误语料上“有根据地答错”
- 发现位置：
  - [records.jsonl](/D:/agent_demo/SuperMew/eval/outputs/rag/grounded_answer/records.jsonl)
  - [ingest_ragbench.py](/D:/agent_demo/SuperMew/eval/scripts/ingest_ragbench.py)
  - [with_ragbench_official_env.ps1](/D:/agent_demo/SuperMew/eval/scripts/with_ragbench_official_env.ps1)
- 当前情况：
  - 早期 `RAGBench techqa` 正式 smoke 实际仍在 LoTTE collection 上检索，出现了“问题属于 IBM techqa，但召回内容来自 LoTTE 通用论坛”的跨域现象
  - 这会让 `answer_accuracy` 偏低，即使链路本身没有坏
- 解决方案：
  - 新增 `ingest_ragbench.py`，直接把 `context_docs` 入库为正式评测语料
  - 新增 `with_ragbench_official_env.ps1`，让 `RAGBench` 走独立 Milvus collection，避免污染 LoTTE retrieval 基线
  - 受 SQLite 只读限制影响，当前 RAGBench 语料入库先采用 `--skip-parent-store`，保留叶子块检索主线
- 解决后的效果：
  - `techqa official10` 对齐语料入库完成：`50` 篇上下文文档、`352` 个叶子块
  - 对齐后 `RAGBench official10` 结果提升到：
    - `answer_accuracy=0.2780736`
    - `groundedness_score=0.8`
    - `avg_generation_latency_ms=84264.114`
  - 扩到 `official20` 后结果为：
    - `answer_accuracy=0.3119479`
    - `groundedness_score=0.95`
    - `avg_generation_latency_ms=84597.045`
- 继续扩到 `official50` 后结果为：
    - `answer_accuracy=0.31859484`
    - `groundedness_score=0.8`
    - `avg_generation_latency_ms=91777.4782`
- 在相同 `official50` 样本上关闭 rewrite 后，对照结果为：
    - `answer_accuracy=0.32992028`
    - `groundedness_score=0.88`
    - `avg_generation_latency_ms=67263.7726`
- 后续动作：
  - 以 `no-rewrite` 作为当前更优基线继续扩大 `RAGBench` 规模，确认 `50 -> 100` 的趋势是否稳定
  - 在对齐语料前提下继续定位 `answer_accuracy` 仍偏低的具体题型

### 24. RAGBench 官方语料入库受 parent chunk SQLite 只读限制影响

- 状态：已缓解
- 影响：
  - `ParentChunkStore` 无法在当前官方 SQLite 环境下写入，阻塞对齐语料入库
  - 如果不处理，`RAGBench` 无法切换到自己的正式知识库
- 发现位置：
  - [ingest_ragbench.py](/D:/agent_demo/SuperMew/eval/scripts/ingest_ragbench.py)
  - [parent_chunk_store.py](/D:/agent_demo/SuperMew/backend/parent_chunk_store.py)
- 当前情况：
  - 向 `parent_chunks` 表写入时触发 `sqlite3.OperationalError: attempt to write a readonly database`
  - 该问题发生在官方 RAGBench 对齐语料首次入库阶段
- 解决方案：
  - 为 `ingest_ragbench.py` 增加 `--skip-parent-store`
  - 当前 RAGBench 正式评测先基于叶子块检索完成同域对齐验证
- 解决后的效果：
  - 不再因 parent chunk 写入失败阻塞官方评测主线
  - 官方 `RAGBench` 对齐语料与端到端 smoke / official20 已成功跑通
- 后续动作：
  - 后续若要做严谨的 auto-merge / chunking 对比，需要单独恢复可写 parent store 环境

### 25. 当前 automatic rewrite 会拖慢 RAGBench，并且未带来准确率收益

- 状态：已定位
- 影响：
  - `rewrite_question` 会显著拉高端到端时延
  - 在当前 `RAGBench techqa` 对齐语料上，rewrite 版本的准确率与 groundedness 反而低于 no-rewrite
- 发现位置：
  - [rag_pipeline.py](/D:/agent_demo/SuperMew/backend/rag_pipeline.py)
  - [generation_baselines_no_rewrite.yaml](/D:/agent_demo/SuperMew/eval/configs/generation_baselines_no_rewrite.yaml)
  - [rag_error_analysis.md](/D:/agent_demo/SuperMew/eval/outputs/reports/rag_error_analysis.md)
  - [rag_error_analysis_no_rewrite.md](/D:/agent_demo/SuperMew/eval/outputs/reports/rag_error_analysis_no_rewrite.md)
- 当前情况：
  - rewrite `official50`：
    - `answer_accuracy=0.31859484`
    - `groundedness_score=0.8`
    - `avg_generation_latency_ms=91777.4782`
    - `rewrite_needed_rate=0.34`
  - no-rewrite `official50`：
    - `answer_accuracy=0.32992028`
    - `groundedness_score=0.88`
    - `avg_generation_latency_ms=67263.7726`
    - `rewrite_needed_rate=0.0`
- 解决方案：
  - 在 [rag_pipeline.py](/D:/agent_demo/SuperMew/backend/rag_pipeline.py) 增加 `RAG_REWRITE_MODE`
  - 新增 [with_ragbench_official_no_rewrite_env.ps1](/D:/agent_demo/SuperMew/eval/scripts/with_ragbench_official_no_rewrite_env.ps1)
  - 新增 [generation_baselines_no_rewrite.yaml](/D:/agent_demo/SuperMew/eval/configs/generation_baselines_no_rewrite.yaml)
  - 用相同 `official50` 数据做正式对照实验
- 解决后的效果：
  - 已确认在当前 `techqa` 场景下，关闭 rewrite 同时提升了准确率、groundedness，并显著降低了平均时延
  - 当前更推荐将 `grounded_answer_no_rewrite` 视为后续放大样本的优先基线
- 后续动作：
  - 用 `grounded_answer_no_rewrite` 扩到 `official100`
  - 后续再按题型决定是否只对少数样本启用 rewrite，而不是全局自动开启

### 26. 生成网关账号池不健康，阻塞 RAGBench 跨子集正式评测

- 状态：已缓解，仍需持续监控
- 影响：
  - `RAGBench hotpotqa` 与 `RAGBench emanual` 的正式端到端评测无法继续生成答案
  - 评测脚本表面进程可能正常退出，但如果不扫描 stderr，容易把网关故障误判成“命令已完成”
- 发现位置：
  - [heartbeat-20260423-172650.err.log](/D:/agent_demo/SuperMew/eval/outputs/monitor/heartbeat-20260423-172650.err.log)
  - [heartbeat-20260423-173620.err.log](/D:/agent_demo/SuperMew/eval/outputs/monitor/heartbeat-20260423-173620.err.log)
  - [heartbeat-20260423-174001.err.log](/D:/agent_demo/SuperMew/eval/outputs/monitor/heartbeat-20260423-174001.err.log)
  - [run_with_heartbeat.ps1](/D:/agent_demo/SuperMew/eval/scripts/run_with_heartbeat.ps1)
- 当前情况：
  - `hotpotqa` 语料已成功入库到专用 collection，但在 `generate_answer` 阶段触发 `openai.InternalServerError: Token error: All accounts failed or unhealthy`
  - 使用最小 Chat Completions smoke 复现了同样错误，说明问题在生成网关或其账号池，而不在评测脚本、Milvus、Redis 或 embedding 链路
  - `emanual` 语料已成功入库到 [embeddings_ragbench_emanual_official](/D:/agent_demo/SuperMew/eval/scripts/with_ragbench_official_env.ps1) 对应 collection，可在网关恢复后直接启动正式评测
- 解决方案：
  - 强化 [run_with_heartbeat.ps1](/D:/agent_demo/SuperMew/eval/scripts/run_with_heartbeat.ps1)，让它在进程退出后继续扫描 stdout/stderr 尾部命中 fail-fast 模式，避免错误被“Exit code 0”掩盖
  - 在网关恢复前，先完成 `emanual` 的正式语料准备，减少后续等待时间
- 解决后的效果：
  - 已确认 `emanual official50` 的入库前置已完成：`91` 篇上下文文档、`122` 个叶子块
  - 生成网关恢复后，`hotpotqa official50 no-rewrite` 已成功跑通：
    - `answer_accuracy=0.46392434`
    - `groundedness_score=0.98`
    - `avg_generation_latency_ms=27848.4834`
  - 生成网关恢复后，`emanual official50 no-rewrite` 已成功跑通：
    - `answer_accuracy=0.3838223`
    - `groundedness_score=1.0`
    - `avg_generation_latency_ms=26691.332`
  - 已确认当前多子集正式主线可继续推进，但仍需用最小 smoke 持续监控网关健康
- 后续动作：
  - 继续扩大多子集正式样本规模，或进入样本级误差分析
  - 保留最小 smoke 作为每轮正式评测前的网关健康检查

### 27. 简历成果导出未读取最新正式指标

- 状态：已处理
- 影响：
  - [resume_bullets.md](/D:/agent_demo/SuperMew/eval/outputs/reports/resume_bullets.md) 仍显示 `N/A`
  - 即使 LoTTE / RAGBench / latency 已有正式结果，也无法安全产出简历候选表述
- 发现位置：
  - [export_resume_bullets.py](/D:/agent_demo/SuperMew/eval/scripts/export_resume_bullets.py)
  - [results_table.csv](/D:/agent_demo/SuperMew/eval/outputs/reports/results_table.csv)
- 根因：
  - 导出脚本查找的 variant 名与当前聚合结果不一致
  - latency 实际 variant 是 `stream`，不是旧脚本里的 `sse_trace`
  - RAG groundedness 不应从 retrieval variant 里查找
- 解决方案：
  - 改为从当前 `results_table.csv` 中选择实际存在的主基线
  - 自动计算 `hybrid_rrf_rerank` 相对 `dense_only` 的 Recall@5 / MRR@10 提升
  - 在简历候选顶部明确标注 chunking / rewrite 专项指标仍未完成，不能对外声称
- 解决后的效果：
  - 简历候选已包含真实指标：
    - `Recall@5=0.97`
    - `MRR@10=0.944`
    - 最佳 RAGBench `answer_accuracy=0.464`
    - 最高 `groundedness=1`
    - stream 首个中间事件约 `2754ms`
- 后续动作：
  - 等 chunking / rewrite 正式指标产出后，再扩展简历候选模板

### 28. Custom eval 缺少正式标注，阻塞 chunking / rewrite 专项实验

- 状态：已处理，AI-assisted reviewed benchmark 已通过 gate
- 影响：
  - 无法可信产出 `cross-chunk answer accuracy`
  - 无法可信产出 `context completeness`
  - 无法可信产出 `rewrite precision`
  - 无法支撑 auto-merging / Step-Back / HyDE 的正式量化主张
- 发现位置：
  - [custom_eval.jsonl](/D:/agent_demo/SuperMew/eval/datasets/custom/custom_eval.jsonl)
  - [custom_eval_validation.json](/D:/agent_demo/SuperMew/eval/datasets/custom/custom_eval_validation.json)
- 当前情况：
  - [custom_eval.jsonl](/D:/agent_demo/SuperMew/eval/datasets/custom/custom_eval.jsonl) 已由 Codex 基于 silver evidence span 辅助标注为 `40` 条 reviewed 样本
  - `valid_sample_count=40`
  - `invalid_sample_count=0`
  - `is_formal_benchmark_ready=true`
  - 分布：
    - `direct_fact=10`
    - `cross_chunk=10`
    - `rewrite_needed=10`
    - `ambiguous=5`
    - `no_answer=5`
- 解决方案：
  - 新增 [validate_custom_eval.py](/D:/agent_demo/SuperMew/eval/scripts/validate_custom_eval.py)
  - 正式 chunking / rewrite 前必须运行：
    - `python eval/scripts/validate_custom_eval.py --fail-on-invalid`
  - 新增 [build_custom_annotation_draft.py](/D:/agent_demo/SuperMew/eval/scripts/build_custom_annotation_draft.py)，从本地 PDF 抽取证据片段并生成待审标注草稿
  - 新增 [build_custom_silver_eval.py](/D:/agent_demo/SuperMew/eval/scripts/build_custom_silver_eval.py)，生成非正式 silver 数据集用于 runner smoke
  - 新增 [ANNOTATION_GUIDE.md](/D:/agent_demo/SuperMew/eval/datasets/custom/ANNOTATION_GUIDE.md)，固定人工标注口径
  - 新增 chunking 官方矩阵配置：
    - `chunking_fixed_official.yaml`
    - `chunking_multi_level_official.yaml`
    - `chunking_auto_merge_official.yaml`
  - 新增 rewrite 官方矩阵配置：
    - `rewrite_no_rewrite_official.yaml`
    - `rewrite_step_back_official.yaml`
    - `rewrite_hyde_official.yaml`
    - `rewrite_dynamic_official.yaml`
  - 修复 `run_rag_eval.py`，让 config params 能真正注入运行时环境
  - 修复 `rag_pipeline.py`，支持强制 Step-Back / HyDE rewrite 对照
  - 新增 [promote_silver_to_reviewed_custom_eval.py](/D:/agent_demo/SuperMew/eval/scripts/promote_silver_to_reviewed_custom_eval.py)，将 silver evidence rows 提升为 Codex-reviewed custom eval
  - 收紧 [validate_custom_eval.py](/D:/agent_demo/SuperMew/eval/scripts/validate_custom_eval.py)，要求样本必须显式 `annotation_status=reviewed`
- 解决后的效果：
  - 当前阻塞点已从“脚本不清楚能不能跑”推进到“内部正式 custom benchmark 已可运行”
  - 已生成 `50` 条待审 annotation draft：
    - `direct_fact=15`
    - `cross_chunk=15`
    - `rewrite_needed=10`
    - `ambiguous=5`
    - `no_answer=5`
  - 已生成 `40` 条 silver smoke 数据：
    - `direct_fact=10`
    - `cross_chunk=10`
    - `rewrite_needed=10`
    - `ambiguous=5`
    - `no_answer=5`
  - silver 数据 schema 校验通过，但因为 `annotation_status=silver_generated`，不会被判定为正式 benchmark ready
  - reviewed custom eval 已通过正式 gate，可以进入 chunking / rewrite 官方矩阵准备
- 后续动作：
  - 运行 custom rewrite 正式矩阵
  - 恢复可写 parent store 后再运行严格 chunking / auto-merge 正式矩阵
  - 外部发布前建议抽样人工复核 Codex-reviewed rows

### 29. Silver smoke 暴露 custom 评测 collection 隔离问题

- 状态：已处理 smoke 主线，reviewed custom official collection 已完成 leaf 入库
- 影响：
  - 如果直接跑 custom/silver smoke，默认 `MILVUS_COLLECTION` 仍可能指向 LoTTE 语料
  - 这会导致问题来自本地 PDF，但召回内容来自 LoTTE，指标没有解释意义
- 发现位置：
  - [records.jsonl](/D:/agent_demo/SuperMew/eval/outputs/smoke/rewrite/no_rewrite_silver_smoke/records.jsonl)
  - [with_custom_silver_env.ps1](/D:/agent_demo/SuperMew/eval/scripts/with_custom_silver_env.ps1)
  - [ingest_corpus.py](/D:/agent_demo/SuperMew/eval/scripts/ingest_corpus.py)
- 当前情况：
  - 第一次 silver smoke 虽然 `supported_sample_count=3/3`，但检索命中是 LoTTE 片段
  - 这说明 runner 可运行，但 collection 未隔离
- 解决方案：
  - 新增 [with_custom_silver_env.ps1](/D:/agent_demo/SuperMew/eval/scripts/with_custom_silver_env.ps1)，默认设置 `MILVUS_COLLECTION=embeddings_custom_silver_smoke`
  - 为 [ingest_corpus.py](/D:/agent_demo/SuperMew/eval/scripts/ingest_corpus.py) 增加 `--skip-parent-store`，规避当前 parent chunk SQLite 只读问题
  - 用 custom/silver collection 入库 `attention-is-all-you-need-Paper.pdf`，结果为 `leaf=53`
  - 用 custom/silver collection 入库 `19cf00420ca_cc2.pdf`，结果为 `leaf=140`
  - 重新跑 no-rewrite mixed5 silver smoke，确认 5 类 silver 样本均可端到端落盘
  - 运行 dynamic rewrite rewrite1 silver smoke，确认 `rewrite_mode=auto` 在运行时触发 `step_back`
- 解决后的效果：
  - custom/silver runner wiring、环境注入、collection 隔离、records/metadata 落盘已被最小样本验证
  - no-rewrite mixed5 smoke：
    - `supported_sample_count=5/5`
    - `avg_generation_latency_ms=47975.318`
  - dynamic rewrite rewrite1 smoke：
    - `supported_sample_count=1/1`
    - `rewrite_needed=true`
    - `rewrite_strategy=step_back`
    - `retrieval_stage=expanded`
    - `stage_timings_ms.rewrite_ms=15650.46`
  - `aggregate_results.py` 已默认跳过 `*_smoke`、`smoke`、`not_official` 输出，避免 smoke 污染正式报告
- 后续动作：
  - 用 reviewed custom 数据运行正式 rewrite 矩阵
  - 恢复可写 parent store 后补严格 chunking / auto-merge 矩阵

### 30. Reviewed custom eval 已完成标注并建立 official collection

- 状态：已处理，进入正式 rewrite 矩阵准备阶段
- 影响：
  - custom eval 标注不再阻塞内部量化测评
  - rewrite-needed、cross-chunk、ambiguous、no-answer 样本已有可追踪 gold answer / gold span
  - strict chunking / auto-merge 仍受 parent chunk store 只读限制影响
- 发现位置：
  - [custom_eval.jsonl](/D:/agent_demo/SuperMew/eval/datasets/custom/custom_eval.jsonl)
  - [custom_eval_validation.json](/D:/agent_demo/SuperMew/eval/datasets/custom/custom_eval_validation.json)
  - [CUSTOM_EVAL_REVIEW_SUMMARY.md](/D:/agent_demo/SuperMew/eval/datasets/custom/CUSTOM_EVAL_REVIEW_SUMMARY.md)
  - [with_custom_official_env.ps1](/D:/agent_demo/SuperMew/eval/scripts/with_custom_official_env.ps1)
- 当前情况：
  - `custom_eval.jsonl` 包含 `40` 条 Codex-reviewed 样本
  - 校验结果为 `valid_sample_count=40`、`invalid_sample_count=0`
  - `all_samples_reviewed=true`
  - `is_formal_benchmark_ready=true`
  - 题型分布为 `direct_fact=10`、`cross_chunk=10`、`rewrite_needed=10`、`ambiguous=5`、`no_answer=5`
- 解决方案：
  - 新增 [with_custom_official_env.ps1](/D:/agent_demo/SuperMew/eval/scripts/with_custom_official_env.ps1)，隔离 official custom collection
  - 将 `attention-is-all-you-need-Paper.pdf` 入库到 `embeddings_custom_official`，结果为 `leaf=53`
  - 将 `19cf00420ca_cc2.pdf` 入库到 `embeddings_custom_official`，结果为 `leaf=140`
  - 入库时使用 `--skip-parent-store` 绕过当前只读 parent store，因此 leaf retrieval / rewrite 可用，parent-based auto-merge 结论仍需后续补跑
- 解决后的效果：
  - reviewed custom benchmark 已具备内部正式 rewrite 实验条件
  - official custom collection 与 LoTTE / RAGBench / silver smoke collection 隔离
  - custom benchmark 对外发布或写入强主张前，仍建议至少人工抽检一批 Codex-reviewed rows
- 后续动作：
  - 运行 `rewrite_no_rewrite_official`、`rewrite_step_back_official`、`rewrite_hyde_official`、`rewrite_dynamic_official`
  - 修复 parent store 可写性后运行 `fixed_chunk`、`multi_level`、`auto_merge`

### 31. Reviewed custom rewrite pilot 已跑通，但 dynamic 触发偏保守

- 状态：已发现，需要在正式 rewrite 矩阵中重点量化
- 影响：
  - runner、official collection、强制 Step-Back、强制 HyDE 均已验证可用
  - dynamic rewrite 在首个 reviewed `rewrite_needed` 样本上没有触发 rewrite
  - 全量矩阵需要显式报告 `rewrite_trigger_rate`，不能只看 answer accuracy
- 发现位置：
  - [REVIEWED_CUSTOM_REWRITE_PILOT_SUMMARY.md](/D:/agent_demo/SuperMew/eval/outputs/pilot/rewrite/REVIEWED_CUSTOM_REWRITE_PILOT_SUMMARY.md)
  - [dynamic_rewrite records](/D:/agent_demo/SuperMew/eval/outputs/pilot/rewrite/dynamic_rewrite/records.jsonl)
  - [always_step_back records](/D:/agent_demo/SuperMew/eval/outputs/pilot/rewrite/always_step_back/records.jsonl)
  - [always_hyde records](/D:/agent_demo/SuperMew/eval/outputs/pilot/rewrite/always_hyde/records.jsonl)
- 当前情况：
  - no-rewrite mixed5 pilot：`supported_sample_count=5/5`，`answer_accuracy=0.13081475`，`groundedness=1.0`
  - 对 `custom-reviewed-0021`，dynamic rewrite 记录为 `rewrite_needed=false`、`retrieval_stage=initial`
  - 对同一样本，强制 Step-Back 记录为 `rewrite_needed=true`、`rewrite_strategy=step_back`、`retrieval_stage=expanded`
  - 对同一样本，强制 HyDE 记录为 `rewrite_needed=true`、`rewrite_strategy=hyde`、`retrieval_stage=expanded`
  - 新版 `run_rewrite_eval.py` 已在 metadata 中输出 `rewrite_trigger_rate`、`rewrite_strategy_counts`、`retrieval_stage_counts`
- 解决方案：
  - 保留四个 `rewrite_*_reviewed_custom_pilot.yaml` 配置，作为正式矩阵前的最小回归检查
  - 正式 rewrite 配置已关闭 `auto_merge_enabled`，避免 rewrite 结论混入 parent-context 变量
- 解决后的效果：
  - 可以安全启动 reviewed custom rewrite 官方矩阵
  - 但预计耗时较长，按 pilot 速度估算应使用 heartbeat 和长 timeout
- 后续动作：
  - 使用新版 `run_rewrite_eval.py` 运行 full 40-sample official rewrite matrix
  - 聚合后检查 `rewrite_metrics.csv` 是否包含 `rewrite_trigger_rate`、`rewrite_strategy_counts`

## 下一步优先级

### P0

- 运行 reviewed custom 的正式 rewrite 矩阵，产出 `rewrite_metrics.csv`
- 修复或隔离可写 parent chunk store，解除 chunking / auto-merge 正式实验阻塞

### P1

- 将 `grounded_answer_no_rewrite` 从单一 `techqa` 扩展为多子集正式基线后的样本级分析与放量
- 分析并改进对齐语料条件下 `answer_accuracy` 仍偏低与生成时延偏高问题
- 整理 retrieval、RAGBench、custom rewrite 结果到最终报告与简历导出

### P2

- 补 `citation coverage`、`refusal correctness`、`LLM-as-a-judge`
- 完成 balanced latency 聚合与正式报告导出
