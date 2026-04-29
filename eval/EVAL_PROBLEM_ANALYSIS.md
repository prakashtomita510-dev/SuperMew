# Quantitative Eval Problem Analysis

这份文档用于对量化测评过程中遇到的关键问题做一次“实现级复盘”。

目标有三个：

- 说明问题到底发生在系统的哪一层，而不是只记录现象
- 给出已经落地的解决方案，以及这些方案和项目实现之间的对应关系
- 保证后续回看时，能从问题直接追到代码、日志、结果文件

这份文档和 [ISSUE_TRACKER.md](./ISSUE_TRACKER.md) 的区别是：

- `ISSUE_TRACKER.md` 更偏过程台账
- 本文档更偏问题分析、根因解释和方案归因

## 1. 当前正式评测状态

截至当前，正式链路已经完成以下结果：

| 类别 | 数据集/变体 | 样本数 | 核心结果 |
| --- | --- | ---: | --- |
| Retrieval | LoTTE `dense_only` | 100 | `Recall@5=0.95`, `MRR@10=0.88` |
| Retrieval | LoTTE `hybrid_rrf_rerank` | 100 | `Recall@5=0.97`, `MRR@10=0.9445` |
| RAG | RAGBench `techqa` `grounded_answer_no_rewrite` | 50 | `answer_accuracy=0.32992028`, `groundedness=0.88` |
| RAG | RAGBench `hotpotqa` `grounded_answer_no_rewrite_hotpotqa` | 50 | `answer_accuracy=0.46392434`, `groundedness=0.98` |
| RAG | RAGBench `emanual` `grounded_answer_no_rewrite_emanual` | 50 | `answer_accuracy=0.3838223`, `groundedness=1.0` |
| Latency | LoTTE stream/sync baseline | 10 | 已产出 `TTFT/trace coverage/duration` 基线 |

结果聚合见：

- [results_summary.md](./outputs/reports/results_summary.md)
- [rag_metrics.csv](./outputs/reports/rag_metrics.csv)
- [retrieval_metrics.csv](./outputs/reports/retrieval_metrics.csv)
- [latency_metrics.csv](./outputs/reports/latency_metrics.csv)

## 2. 问题总览

本轮正式测评里，真正影响可信度和推进速度的问题，主要集中在 7 类：

| 编号 | 问题 | 影响层 | 当前状态 |
| --- | --- | --- | --- |
| P1 | 官方评测会退回 mock / fallback | 评测可信度 | 已解决 |
| P2 | BM25 与向量库语料不同步 | 检索有效性 | 已解决 |
| P3 | `rag_trace` 不完整 | 可追溯性 / latency | 已解决 |
| P4 | RAGBench 误用 LoTTE 语料 | 端到端结果解释性 | 已解决 |
| P5 | automatic rewrite 在当前实现里收益为负 | 质量 / 时延 | 已定位并切换基线 |
| P6 | 外部服务不稳定：embedding 限流与生成网关波动 | 推进效率 / 任务稳定性 | 已缓解，需持续监控 |
| P7 | 运行监控不足，错误可能被长任务掩盖 | 执行可靠性 | 已解决 |

下面按“现象 -> 根因 -> 实现方案 -> 结果变化”展开。

## 3. P1 官方评测会退回 mock / fallback

### 现象

早期在本地环境里，即使真实 Milvus 没准备好，评测脚本仍可能继续执行，并给出一份“看起来像结果”的输出。

这会直接污染：

- `Recall@5`
- `MRR@10`
- `TTFT`
- `trace coverage rate`

### 根因

评测 runner 和底层向量库调用之间，缺少一个“正式模式必须是真实链路”的硬约束。

### 实现证据

- [milvus_client.py](../backend/milvus_client.py)
- [run_retrieval_eval.py](./scripts/run_retrieval_eval.py)
- [run_rag_eval.py](./scripts/run_rag_eval.py)
- [with_official_eval_env.ps1](./scripts/with_official_eval_env.ps1)

### 解决方案

- 增加 `MILVUS_REQUIRE_REAL=true`
- 官方模式下，如果 backend 不是正式 Milvus，则样本记为 `unsupported`
- 当 `supported_sample_count == 0` 时，runner 必须非零退出

### 解决后的效果

- mock 结果不再混入正式报告
- 当前所有主报告结果都来自真实 Milvus + 真实 embedding + 真实生成链路

## 4. P2 BM25 与向量库语料不同步

### 现象

早期 `sparse_only` 和 `hybrid` 的表现不稳定，甚至会出现明显不合理的空结果或排序漂移。

### 根因

稀疏检索依赖 BM25 状态，但文档写入、删除和查询之间没有保证使用同一份统计状态。

换句话说，dense 在看一套语料，sparse 在看另一套语料。

### 实现证据

- [embedding.py](../backend/embedding.py)
- [milvus_writer.py](../backend/milvus_writer.py)
- [api.py](../backend/api.py)

### 解决方案

- BM25 状态支持保存、加载、刷新
- 上传 / 删除文档后触发稀疏语料重建
- 写入阶段把已有 leaf chunk 和新增 chunk 放进同一统计视图

### 解决后的效果

- dense / sparse / hybrid 基线开始可解释
- 当前 LoTTE 正式 retrieval 能稳定产出四个变体结果

## 5. P3 `rag_trace` 不完整，无法支撑可追溯评测

### 现象

早期样本级结果虽然有最终回答，但缺少足够的内部状态，导致下面这些问题无法回答：

- 到底检索到了哪些块
- rewrite 有没有触发
- latency 高是检索慢、改写慢还是生成慢

### 根因

`rag_trace` 里缺少关键字段，SSE 事件和最终 trace 也没有统一上下文。

### 实现证据

- [rag_pipeline.py](../backend/rag_pipeline.py)
- [agent.py](../backend/agent.py)
- [tools.py](../backend/tools.py)
- [schemas.py](../backend/schemas.py)

### 解决方案

- 补齐 `vector_backend`、`tool_name`、`initial_retrieved_chunks`
- 增加 `request_id`
- 增加 `stage_timings_ms`
- SSE 事件和最终 trace 共享请求上下文

### 解决后的效果

- latency 评测已经能落出 `TTFT`、`TTFM`、阶段耗时
- 样本级 `records.jsonl` 已足以支持误差分析
- 后续 `analyze_rag_eval.py` 才有基础做 `rewrite_ms / retrieve_ms / generate_ms` 分解

## 6. P4 RAGBench 误用 LoTTE 语料，导致端到端结果失真

### 现象

早期 `RAGBench techqa` 的问题，在回答时实际召回的却是 LoTTE 论坛语料。这会出现一种很迷惑的情况：

- `groundedness` 看起来不一定低
- 但 `answer_accuracy` 很差

### 根因

评测脚本能跑，但检索 collection 没有按数据集隔离，导致 RAGBench 评测混用了 LoTTE 语料。

### 实现证据

- [ingest_ragbench.py](./scripts/ingest_ragbench.py)
- [with_ragbench_official_env.ps1](./scripts/with_ragbench_official_env.ps1)
- [grounded_answer/records.jsonl](./outputs/rag/grounded_answer/records.jsonl)

### 解决方案

- 新增 `ingest_ragbench.py`，把 `context_docs` 转成正式检索语料
- 用 `with_ragbench_official_env.ps1` 为不同 subset 指定独立 `MILVUS_COLLECTION`
- 先允许 `--skip-parent-store`，避开只读 SQLite 对 parent chunk 的阻塞

### 解决后的效果

- `techqa` 从“跨域检索”变成“同域检索”
- 后续 `techqa official50`、`hotpotqa official50`、`emanual official50` 都建立在各自 collection 上

## 7. P5 automatic rewrite 在当前实现里收益为负

### 现象

直觉上，自动改写应该帮助复杂问题，但在当前 `RAGBench techqa` 的正式对照中，rewrite 版本反而：

- 更慢
- groundedness 更低
- answer accuracy 也更低

### 根因

当前系统的 rewrite 触发条件和生成侧收益并不匹配。它更像是在一部分样本上增加了额外推理与改写成本，但没有稳定提升召回或答案抽取质量。

### 实现证据

- [rag_pipeline.py](../backend/rag_pipeline.py)
- [generation_baselines_no_rewrite.yaml](./configs/generation_baselines_no_rewrite.yaml)
- [rag_error_analysis.md](./outputs/reports/rag_error_analysis.md)
- [rag_error_analysis_no_rewrite.md](./outputs/reports/rag_error_analysis_no_rewrite.md)

代码上，关键控制点是：

- `RAG_REWRITE_MODE = os.getenv("RAG_REWRITE_MODE", "auto")`
- 当 `RAG_REWRITE_MODE == "off"` 时，`grade_documents_node` 直接走 `generate_answer`
- `rewrite_question_node` 返回禁用状态，不再增加 rewrite 阶段开销

### 正式对照结果

`techqa official50`

- rewrite:
  - `answer_accuracy=0.31859484`
  - `groundedness_score=0.8`
  - `avg_generation_latency_ms=91777.4782`
- no-rewrite:
  - `answer_accuracy=0.32992028`
  - `groundedness_score=0.88`
  - `avg_generation_latency_ms=67263.7726`

### 解决方案

- 在 [rag_pipeline.py](../backend/rag_pipeline.py) 中引入 `RAG_REWRITE_MODE`
- 新增：
  - [with_ragbench_official_no_rewrite_env.ps1](./scripts/with_ragbench_official_no_rewrite_env.ps1)
  - [generation_baselines_no_rewrite_hotpotqa.yaml](./configs/generation_baselines_no_rewrite_hotpotqa.yaml)
  - [generation_baselines_no_rewrite_emanual.yaml](./configs/generation_baselines_no_rewrite_emanual.yaml)

### 解决后的效果

当前正式主基线已经切换为 `no-rewrite`，并成功推广到了三个 subset：

- `techqa`
- `hotpotqa`
- `emanual`

## 8. P6 外部服务不稳定：embedding 限流与生成网关波动

### 现象

这一类问题不是代码逻辑错误，但会直接影响测评推进速度和结果可产出性。

主要表现为两类：

- embedding 侧：限流、认证、接口兼容性问题
- generation 侧：账号池不健康、网关临时不可用

### 根因

评测流程依赖外部模型服务，且不同服务商的接口约束并不一致。

在本项目里，确实踩到了这些具体问题：

- Cohere trial key 配额不足
- Google embedding 的接口路径与项目原实现不兼容
- SiliconFlow OpenAI-compatible embedding 请求头不完整
- 生成网关曾出现 `All accounts failed or unhealthy`

### 实现证据

- [embedding.py](../backend/embedding.py)
- [smoke_generation_gateway.py](./scripts/smoke_generation_gateway.py)
- [heartbeat-20260423-174001.err.log](./outputs/monitor/heartbeat-20260423-174001.err.log)
- [heartbeat-20260423-190251.out.log](./outputs/monitor/heartbeat-20260423-190251.out.log)

### 解决方案

embedding 侧：

- 给 `EmbeddingService` 增加 provider 兼容逻辑
- 支持从 `.env` 同时读取：
  - `EMBEDDER`
  - `EMBEDDING_MODEL`
  - `EMBEDDING_DIMENSION`
  - `EMBEDDING_OUTPUT_DIM`
- 对 Cohere 增加节流与批大小控制
- 对 SiliconFlow 补齐 `Authorization: Bearer ...`

generation 侧：

- 增加最小 smoke 脚本 [smoke_generation_gateway.py](./scripts/smoke_generation_gateway.py)
- 每次正式大任务前先做最小网关健康检查

### 解决后的效果

- embedding 主链路已稳定切到 `Pro/BAAI/bge-m3`，当前维度是 `1024`
- 生成网关恢复后，`hotpotqa` 与 `emanual` 已成功跑通正式结果

## 9. P7 运行监控不足，错误可能被长任务掩盖

### 现象

早期最大的执行风险不是“立刻报错”，而是：

- 命令已经失败
- 但任务还在运行很久
- 或者 PowerShell 退出码看起来是 `0`
- 实际 stderr 里早就有 traceback

这会直接浪费大量时间。

### 根因

单纯依赖进程退出码，不足以监控这种长链路任务。外部脚本或包装器有时会吞掉错误码。

### 实现证据

- [run_with_heartbeat.ps1](./scripts/run_with_heartbeat.ps1)

关键实现包括：

- 30 秒心跳
- stdout/stderr tail 输出
- fail-fast pattern 检测
- 进程退出后继续扫描最终 stderr / stdout

### 解决方案

- 所有长任务统一走 `run_with_heartbeat.ps1`
- 关键模式如：
  - `Traceback`
  - `InternalServerError`
  - `429`
  - `All accounts failed or unhealthy`
  一旦命中就立即判失败

### 解决后的效果

- 后续没有再出现“20 小时空跑”那类问题
- `hotpotqa` 网关故障和后续恢复，都能被快速、明确地识别

## 10. 官方评测环境里禁止联网搜索是正确决策

### 现象

早期 latency / trace 覆盖率出现过异常波动，原因之一是 Agent 在评测中可能调用联网搜索工具，引入额外的不稳定网络依赖。

### 根因

正式评测目标是评估本项目的 RAG 实现，而不是把外部互联网搜索混进来。

### 实现证据

- [tools.py](../backend/tools.py)
- [agent.py](../backend/agent.py)
- [with_official_eval_env.ps1](./scripts/with_official_eval_env.ps1)

### 解决方案

- 官方评测环境统一注入 `DISABLE_INTERNET_CRAWLER_SEARCH=true`
- Agent 构建时不再挂 `internet_crawler_search`

### 解决后的效果

- DuckDuckGo 相关告警消失
- 官方评测 latency 与 trace 覆盖率变得更稳定
- 评测对象边界更清晰：只测项目内生 RAG 能力

## 11. 当前阶段的核心结论

从“第一性原理”的角度看，这次量化测评里真正重要的不是脚本数量，而是三个判断：

### 11.1 当前正式基线应该是 `no-rewrite`

这是已经被三个层面的证据共同支持的：

- `techqa` 正式对照结果
- `hotpotqa` 正式结果
- `emanual` 正式结果

所以后续如果继续放大样本，应该默认放大 `no-rewrite`，而不是回到 automatic rewrite。

### 11.2 当前瓶颈更偏“答案抽取质量”，而不是“是否 grounded”

从多个误差分析看，很多低分样本是：

- `groundedness_score` 很高
- 但 `answer_accuracy` 仍然偏低

这说明当前系统更像是“找到了相关材料，但答案组织和抽取还不够准”，而不是典型 hallucination。

### 11.3 外部服务健康检查必须成为正式评测的固定前置

当前已经证明：

- 只要 embedding 或 generation 网关不稳
- 再好的脚本也跑不出可靠结果

所以后续正式评测流程应该固定为：

1. 先跑最小 smoke
2. 再跑正式任务
3. 全程用 heartbeat 监控

## 12. 下一步建议

建议按这个顺序继续：

1. 基于现有三个 subset 的 `no-rewrite official50`，做统一样本级误差归类
2. 优先处理“高 groundedness、低 accuracy”的答案抽取问题
3. 再决定是否扩大到更大正式样本规模
4. 等 parent chunk 可写环境恢复后，再补 auto-merge / chunking 的严格对比

## 13. 关键引用

- 实现层：
  - [rag_pipeline.py](../backend/rag_pipeline.py)
  - [embedding.py](../backend/embedding.py)
  - [agent.py](../backend/agent.py)
  - [tools.py](../backend/tools.py)
- 评测脚本：
  - [run_with_heartbeat.ps1](./scripts/run_with_heartbeat.ps1)
  - [ingest_ragbench.py](./scripts/ingest_ragbench.py)
  - [aggregate_results.py](./scripts/aggregate_results.py)
  - [analyze_rag_eval.py](./scripts/analyze_rag_eval.py)
  - [smoke_generation_gateway.py](./scripts/smoke_generation_gateway.py)
- 结果与台账：
  - [results_summary.md](./outputs/reports/results_summary.md)
  - [ISSUE_TRACKER.md](./ISSUE_TRACKER.md)
  - [rag_error_analysis_no_rewrite_hotpotqa.md](./outputs/reports/rag_error_analysis_no_rewrite_hotpotqa.md)
  - [rag_error_analysis_no_rewrite_emanual.md](./outputs/reports/rag_error_analysis_no_rewrite_emanual.md)
