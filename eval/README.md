# RAG Eval Pipeline

`eval/` 用来承载这套 RAG 系统的离线评测工程。当前版本已经具备：

- 统一的配置与结果写出约定
- LoTTE / RAGBench / custom dataset 的本地骨架
- retrieval / chunking / rewrite / rag / latency 五类脚本入口
- 汇总报表与简历描述导出脚本

当前测评进度、可信结果、缺口和下一步计划见：

- [EVAL_PROGRESS_AND_NEXT_PLAN.md](./EVAL_PROGRESS_AND_NEXT_PLAN.md)
- [EVAL_IMPROVEMENT_TASK_BOARD.md](./EVAL_IMPROVEMENT_TASK_BOARD.md)

## 当前正式结果快照

截至 2026-04-25，当前已经可以追溯引用的正式结果包括：

- LoTTE technology official 100 retrieval matrix：
  - `dense_only`: `Recall@5=0.95`, `MRR@10=0.88`
  - `hybrid_rrf_rerank`: `Recall@5=0.97`, `MRR@10=0.9445`
- RAGBench official 50 no-rewrite bas线：
  - `techqa`: `answer_accuracy=0.32992028`, `groundedness=0.88`
  - `hotpotqa`: `answer_accuracy=0.46392434`, `groundedness=0.98`
  - `emanual`: `answer_accuracy=0.3838223`, `groundedness=1.0`
- Latency / trace baseline：
  - `stream`: 首个中间事件平均约 `2754ms`，`trace_coverage_rate=1.0`，但当前只有 3 条样本
  - `sync`: 10 条样本平均端到端时延约 `25534ms`，`trace_coverage_rate=0.3`
- Reviewed custom official 40 rewrite matrix：
  - `no_rewrite`: `answer_accuracy=0.05951734`, `rewrite_trigger_rate=0.0`, `avg_generation_latency_ms=46885.81975`
  - `always_step_back`: `answer_accuracy=0.0600714`, `rewrite_trigger_rate=1.0`, `avg_generation_latency_ms=55428.805`
  - `always_hyde`: `answer_accuracy=0.06117123`, `rewrite_trigger_rate=1.0`, `avg_generation_latency_ms=51538.9455`
  - `dynamic_rewrite`: `answer_accuracy=0.06553643`, `rewrite_trigger_rate=0.275`, `avg_generation_latency_ms=59629.152`

仍未形成正式主张的部分：

- `chunking_metrics.csv` 仍为空，暂不能声称 auto-merging / cross-chunk 指标提升
- `rewrite_metrics.csv` 已有正式矩阵结果，但需要按题型和触发正确性做样本级分析后再形成强主张
- `custom_eval.jsonl` 已有 40 条 Codex-reviewed 样本并通过内部正式 gate；外部发布前仍建议抽样人工复核

正式评测的硬约束：

- 正式结果只认真实服务链路
- 不允许把 `mock_milvus` / fallback 结果混入最终主报告
- 每次运行都要保留 config snapshot、样本级结果、聚合结果

## 目录

- `configs/`
  - `retrieval_baselines.yaml`
  - `chunking_baselines.yaml`
  - `chunking_fixed_official.yaml`
  - `chunking_multi_level_official.yaml`
  - `chunking_auto_merge_official.yaml`
  - `generation_baselines.yaml`
  - `latency_eval.yaml`
  - `rewrite_no_rewrite_official.yaml`
  - `rewrite_step_back_official.yaml`
  - `rewrite_hyde_official.yaml`
  - `rewrite_dynamic_official.yaml`
- `datasets/`
  - `lotte/`
  - `ragbench/`
  - `custom/`
- `scripts/`
  - `download_lotte.py`
  - `download_ragbench.py`
  - `build_custom_eval.py`
  - `ingest_corpus.py`
  - `run_retrieval_eval.py`
  - `run_chunking_eval.py`
  - `run_rewrite_eval.py`
  - `run_rag_eval.py`
  - `run_latency_eval.py`
  - `aggregate_results.py`
  - `export_resume_bullets.py`
- `outputs/`
  - `retrieval/`
  - `chunking/`
  - `rewrite/`
  - `rag/`
  - `latency/`
  - `reports/`

## 环境准备

建议使用项目已有虚拟环境，并确保以下服务在正式评测时可用：

- 真实 Milvus
- embedding API
- rerank API
- 数据库 / Redis

正式评测前请设置：

```env
MILVUS_REQUIRE_REAL=true
```

这样在真实 Milvus 不可用时，脚本会直接失败，而不是静默退到 mock。

建议在正式开跑前先执行：

```bash
python eval/scripts/check_official_readiness.py
```

当前自检会检查：

- 真实 Milvus 地址是否合法且可连通
- Model Gateway / Embedding / Rerank 接口是否可用
- Redis 是否可连通
- 本地数据库路径是否可写

正式长任务建议统一按以下顺序执行：

1. 运行 `check_official_readiness.py`
2. 运行 `smoke_generation_gateway.py`
3. 确认 `MILVUS_REQUIRE_REAL=true`
4. 确认正式评测环境禁用联网搜索：`DISABLE_INTERNET_CRAWLER_SEARCH=true`
5. 使用 `run_with_heartbeat.ps1` 包装长任务
6. 检查输出目录中是否同时存在：
   - `metadata.json`
   - `records.jsonl`
   - `summary.md`
7. 运行：

```bash
python eval/scripts/aggregate_results.py --outputs-root eval/outputs
python eval/scripts/export_resume_bullets.py
```

## 数据准备

### 1. 生成 LoTTE / RAGBench 本地 manifest

```bash
python eval/scripts/download_lotte.py
python eval/scripts/download_ragbench.py
```

当前已经接到 Hugging Face dataset viewer API，可以直接用 `--download` 拉取标准化样本。

### 2. 生成 custom eval 草稿

```bash
python eval/scripts/build_custom_eval.py --max-samples 20
```

当前版本会基于 `data/documents/` 生成草稿样本；其中 `gold_answer`、`gold_spans`、`question_type` 仍需要人工补标。

正式运行 chunking / rewrite 前必须先校验 custom eval：

```bash
python eval/scripts/validate_custom_eval.py --fail-on-invalid
```

校验结果会写入：

- `eval/datasets/custom/custom_eval_validation.json`

当前 custom eval 状态：

- `sample_count=40`
- `valid_sample_count=40`
- `is_formal_benchmark_ready=true`
- `annotation_status=reviewed`
- 最小正式门槛：`40` 条已核验样本

当前 `custom_eval.jsonl` 已通过 gate，可以用于后续正式 chunking / rewrite runner。该版本由 Codex 基于证据片段辅助标注，外部发布前仍建议抽样复核。

标注结果小结见：

- `eval/datasets/custom/CUSTOM_EVAL_REVIEW_SUMMARY.md`

为了降低标注成本，可以先生成待审草稿包：

```bash
.venv_311\Scripts\python.exe eval/scripts/build_custom_annotation_draft.py --max-samples 50
```

该脚本会从 `data/documents/` 抽取 PDF 证据片段并写出：

- `eval/datasets/custom/custom_eval_annotation_draft.jsonl`
- `eval/datasets/custom/custom_eval_annotation_draft.manifest.json`

标注口径见：

- `eval/datasets/custom/ANNOTATION_GUIDE.md`

也可以生成非正式 silver 数据集用于 runner smoke：

```bash
python eval/scripts/build_custom_silver_eval.py --max-samples 40
python eval/scripts/validate_custom_eval.py ^
  --dataset-path eval/datasets/custom/custom_eval_silver.jsonl ^
  --report-path eval/datasets/custom/custom_eval_silver_validation.json
```

silver 数据集只用于流程联调，`annotation_status=silver_generated`，不会被 validator 判定为正式 benchmark ready。

如需对 custom/silver 使用隔离 Milvus collection：

```bash
powershell -ExecutionPolicy Bypass -File eval/scripts/with_custom_silver_env.ps1 ^
  .\.venv_311\Scripts\python.exe eval/scripts/ingest_corpus.py ^
  --source-dir data/documents ^
  --glob attention-is-all-you-need-Paper.pdf ^
  --skip-parent-store
```

当前已用 `embeddings_custom_silver_smoke` collection 完成了 `attention-is-all-you-need-Paper.pdf` 的叶子块入库：`leaf=53`。

后续也已入库：

- `19cf00420ca_cc2.pdf`: `leaf=140`

silver smoke 结果小结见：

- `eval/outputs/smoke/SMOKE_SUMMARY.md`

reviewed custom eval 的正式 collection：

- `MILVUS_COLLECTION=embeddings_custom_official`
- `attention-is-all-you-need-Paper.pdf`: `leaf=53`
- `19cf00420ca_cc2.pdf`: `leaf=140`

入库命令形态：

```bash
powershell -ExecutionPolicy Bypass -File eval/scripts/with_custom_official_env.ps1 ^
  .\.venv_311\Scripts\python.exe eval/scripts/ingest_corpus.py ^
  --source-dir data/documents ^
  --glob attention-is-all-you-need-Paper.pdf ^
  --skip-parent-store
```

当前 parent chunk store 仍受 SQLite 只读限制影响，所以 reviewed custom official collection 先具备叶子块检索能力；严格 auto-merging / parent-context 对比需要恢复可写 parent store 后再跑。

reviewed custom rewrite pilot 已完成，结果见：

- `eval/outputs/pilot/rewrite/REVIEWED_CUSTOM_REWRITE_PILOT_SUMMARY.md`

pilot 结果只用于正式矩阵前的链路验证，不进入最终报告。

### 3. 文档入库

```bash
python eval/scripts/ingest_corpus.py --source-dir data/documents
```

## 运行方式

### Retrieval Eval

```bash
python eval/scripts/run_retrieval_eval.py ^
  --config eval/configs/retrieval_baselines.yaml ^
  --dataset-path eval/datasets/lotte/normalized/technology/dev.jsonl
```

### Chunking Eval

正式矩阵配置已经准备好，custom eval 已通过校验；但当前 parent chunk store 仍受 SQLite 只读限制影响，因此严格 auto-merging / parent-context 结论需要恢复可写 parent store 后再发布。

```bash
python eval/scripts/run_chunking_eval.py ^
  --config eval/configs/chunking_auto_merge_official.yaml ^
  --dataset-path eval/datasets/custom/custom_eval.jsonl
```

推荐矩阵：

- `eval/configs/chunking_fixed_official.yaml`
- `eval/configs/chunking_multi_level_official.yaml`
- `eval/configs/chunking_auto_merge_official.yaml`

### Rewrite Eval

正式矩阵配置已经准备好，custom eval 已通过校验，reviewed custom official collection 也已完成 leaf 入库；可以优先运行 rewrite 矩阵。

```bash
python eval/scripts/run_rewrite_eval.py ^
  --config eval/configs/rewrite_dynamic_official.yaml ^
  --dataset-path eval/datasets/custom/custom_eval.jsonl
```

推荐矩阵：

- `eval/configs/rewrite_no_rewrite_official.yaml`
- `eval/configs/rewrite_step_back_official.yaml`
- `eval/configs/rewrite_hyde_official.yaml`
- `eval/configs/rewrite_dynamic_official.yaml`

一键长跑脚本：

```bash
powershell -ExecutionPolicy Bypass -File eval/scripts/run_custom_rewrite_official_matrix.ps1
```

该脚本会使用 `with_custom_official_env.ps1`、heartbeat wrapper 和 `custom_eval.jsonl` 顺序运行四个正式 rewrite 配置，并在结束后重新聚合报告。

### RAG Eval

```bash
python eval/scripts/run_rag_eval.py ^
  --config eval/configs/generation_baselines.yaml ^
  --dataset-path eval/datasets/ragbench/normalized/techqa/test.jsonl
```

### Latency Eval

```bash
python eval/scripts/run_latency_eval.py ^
  --config eval/configs/latency_eval.yaml
```

## 汇总与报告

聚合所有已生成实验结果：

```bash
python eval/scripts/aggregate_results.py --outputs-root eval/outputs
```

当前聚合脚本会对同一 `kind + dataset + variant` 只保留最新一次 `metadata.json`，避免历史 smoke / pilot / 旧模型结果混入当前总表。

默认聚合会跳过 `*_smoke`、`smoke`、`not_official` 输出。若需要调试 smoke 结果，可显式加：

```bash
python eval/scripts/aggregate_results.py --outputs-root eval/outputs --include-smoke
```

导出简历表述候选：

```bash
python eval/scripts/export_resume_bullets.py
```

## 输出文件

聚合后的核心文件位于 `eval/outputs/reports/`：

- `results_summary.md`
- `results_table.csv`
- `retrieval_metrics.csv`
- `chunking_metrics.csv`
- `rewrite_metrics.csv`
- `latency_metrics.csv`
- `rag_metrics.csv`
- `resume_bullets.md`

## 当前已知缺口

- LoTTE / RAGBench 已接入 Hugging Face dataset viewer API，但目前默认只拉取标准化问答样本，不含完整 LoTTE 语料入库流程
- custom eval 已完成 Codex-reviewed 标注并通过内部正式 gate；对外发布或强主张前仍建议抽样人工复核
- retrieval runner 已能跑当前 backend，但完整的 `dense_only / sparse_only / hybrid_rrf / hybrid_rrf_rerank` 变体切换还需要继续补 backend 开关
- citation coverage、refusal correctness、LLM-as-a-judge 仍需继续补到正式版
