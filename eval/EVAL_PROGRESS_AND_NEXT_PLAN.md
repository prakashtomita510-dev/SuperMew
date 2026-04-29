# RAG Eval Progress And Next Plan

Last updated: 2026-04-25

This document summarizes the current quantitative evaluation work under `eval/`, compares it with the original task list in `docs/rag_eval_tasklist.pdf`, and records the next execution plan with traceable evidence.

## 1. Executive Summary

**[Update 2026-04-28]**
- **P1-01 (Weight Sweep)** & **P2-01 (Latency Stream vs Sync)** have completed. The optimal configuration for general latency and semantic performance has been identified as `dense_only` retrieval coupled with `stream=True` generation. This configuration has been committed to the formal `.env` defaults and RAG logic.
- **P1-02 (Rerank Cost Optimization)** is actively running to determine the optimal `candidate_k` for reranking latency vs. accuracy tradeoffs.


The evaluation work has moved past scaffolding and now has real official results for three major tracks:

- LoTTE retrieval baseline: `dense_only`, `sparse_only`, `hybrid_rrf`, `hybrid_rrf_rerank`
- RAGBench end-to-end baseline: `techqa`, `hotpotqa`, `emanual`
- Latency and observability baseline: `sync` and `stream`

The most reliable current headline is:

- On LoTTE official 100 samples, `hybrid_rrf_rerank` reaches `Recall@5=0.97` and `MRR@10=0.9445`.
- Compared with `dense_only`, `hybrid_rrf_rerank` improves `Recall@5` from `0.95` to `0.97` and `MRR@10` from `0.88` to `0.9445`, but raises average retrieval latency from about `159ms` to about `1335ms`.
- On RAGBench official 50-sample subsets, `no-rewrite` is currently the stronger generation baseline. For `techqa`, disabling rewrite improves `answer_accuracy` from `0.31859484` to `0.32992028`, improves groundedness from `0.8` to `0.88`, and reduces average generation latency from about `91.8s` to about `67.3s`.

The main unfinished parts are also clear:

- `chunking_metrics.csv` is still empty.
- `rewrite_metrics.csv` is now populated by the reviewed custom official matrix, but needs sample-level interpretation before making a strong public claim.
- `custom_eval.jsonl` now has 40 AI-assisted reviewed rows and passes the formal validation gate.
- `validate_custom_eval.py` now writes `eval/datasets/custom/custom_eval_validation.json`; the current validation result is `sample_count=40`, `valid_sample_count=40`, `is_formal_benchmark_ready=true`.
- `build_custom_annotation_draft.py` now creates a 50-row annotation draft pack from local PDF evidence spans, with distribution `direct_fact=15`, `cross_chunk=15`, `rewrite_needed=10`, `ambiguous=5`, `no_answer=5`.
- `build_custom_silver_eval.py` now creates a 40-row non-official silver dataset for runner smoke, with balanced coverage of direct, cross-chunk, rewrite, ambiguous, and no-answer cases.
- A no-rewrite silver smoke run has confirmed the runner can write sample-level outputs on `custom_silver`; it also exposed the need for dataset-specific Milvus collections.
- The custom/silver smoke collection now contains both local source documents and has run no-rewrite mixed5 plus dynamic rewrite rewrite1 smoke tests successfully.
- A dedicated reviewed custom official collection, `embeddings_custom_official`, now contains both local source documents as leaf chunks.
- Reviewed custom rewrite pilots now run on `embeddings_custom_official`; dynamic did not trigger rewrite on the first reviewed `rewrite_needed` sample, while forced Step-Back and HyDE did use expanded retrieval.
- `resume_bullets.md` has been regenerated from current reports and now includes real retrieval, RAGBench, and latency numbers.
- Chunking and rewrite official matrix config files have been added. Rewrite official matrix has run on reviewed custom eval; strict chunking / auto-merge still needs a writable parent chunk store.
- Latency results are usable as a baseline, but `stream` and `sync` sample sizes differ, so direct comparison should be treated carefully.

## 2. Source Documents And Evidence

Primary requirement:

- Original task list: `docs/rag_eval_tasklist.pdf`
- Extracted text for review: `eval/tasklist_text_utf8.txt`

Current state documents:

- Eval entrypoint: `eval/README.md`
- Process issue log: `eval/ISSUE_TRACKER.md`
- Problem/root-cause analysis: `eval/EVAL_PROBLEM_ANALYSIS.md`
- Improvement task board: `eval/EVAL_IMPROVEMENT_TASK_BOARD.md`

Aggregated reports:

- Summary: `eval/outputs/reports/results_summary.md`
- Retrieval metrics: `eval/outputs/reports/retrieval_metrics.csv`
- RAG metrics: `eval/outputs/reports/rag_metrics.csv`
- Latency metrics: `eval/outputs/reports/latency_metrics.csv`
- Chunking metrics: `eval/outputs/reports/chunking_metrics.csv`
- Rewrite metrics: `eval/outputs/reports/rewrite_metrics.csv`
- Resume bullets: `eval/outputs/reports/resume_bullets.md`
- Custom eval validation: `eval/datasets/custom/custom_eval_validation.json`
- Custom eval review summary: `eval/datasets/custom/CUSTOM_EVAL_REVIEW_SUMMARY.md`
- Custom eval annotation draft: `eval/datasets/custom/custom_eval_annotation_draft.jsonl`
- Custom eval annotation guide: `eval/datasets/custom/ANNOTATION_GUIDE.md`
- Custom silver eval: `eval/datasets/custom/custom_eval_silver.jsonl`
- Custom silver smoke output: `eval/outputs/smoke/rewrite/no_rewrite_silver_smoke/metadata.json`
- Silver smoke summary: `eval/outputs/smoke/SMOKE_SUMMARY.md`
- Reviewed custom rewrite pilot summary: `eval/outputs/pilot/rewrite/REVIEWED_CUSTOM_REWRITE_PILOT_SUMMARY.md`
- Full custom rewrite matrix runner: `eval/scripts/run_custom_rewrite_official_matrix.ps1`

Sample-level and run-level traceability:

- Retrieval official outputs: `eval/outputs/retrieval_official/*/{metadata.json,records.jsonl,summary.md}`
- RAG outputs: `eval/outputs/rag/*/{metadata.json,records.jsonl,summary.md}`
- Latency official outputs: `eval/outputs/latency_official/*/{metadata.json,records.jsonl}`
- Long-run logs: `eval/outputs/monitor/*.out.log` and `eval/outputs/monitor/*.err.log`

## 3. Requirement Coverage

| Area from task list | Current status | Evidence | Assessment |
| --- | --- | --- | --- |
| Evaluation directory structure | Mostly complete | `eval/configs`, `eval/datasets`, `eval/scripts`, `eval/outputs` | The required skeleton exists and has real runners. |
| LoTTE retrieval evaluation | Partially complete with official results | `eval/outputs/reports/retrieval_metrics.csv` | Technology-domain official 100-sample matrix is complete; broader domains and larger sample sizes remain. |
| RAGBench end-to-end evaluation | Partially complete with official results | `eval/outputs/reports/rag_metrics.csv` | Three 50-sample subsets are complete; larger and more stable benchmark slices remain. |
| Custom benchmark | Complete enough for internal official runs | `eval/datasets/custom/custom_eval.jsonl`, `custom_eval_validation.json` | 40 AI-assisted reviewed samples pass validation. Spot-check before external publication. |
| Chunking / auto-merging eval | Not complete | empty `eval/outputs/reports/chunking_metrics.csv` | Runner/configs exist, but official metrics are not produced. |
| Query rewrite eval | Complete for the reviewed custom official matrix | `eval/outputs/reports/rewrite_metrics.csv`, `eval/outputs/rewrite/*/metadata.json` | 40-sample matrix has run for no-rewrite, Step-Back, HyDE, and dynamic rewrite. Needs sample-level interpretation before external claims. |
| SSE / latency observability | Partially complete | `eval/outputs/reports/latency_metrics.csv` | Official sync/stream runs exist. Trace coverage improved after disabling internet search, but sample sizes differ. |
| Report aggregation | Mostly complete | `aggregate_results.py`, `results_summary.md`, CSV files | Aggregation keeps latest result per `kind + dataset + variant`; good enough for current tracking. |
| Resume bullet export | Mostly complete | `resume_bullets.md` | Export now reflects current retrieval, RAGBench, and latency numbers; chunking/rewrite claims remain explicitly pending. |
| Reproducibility and traceability | Mostly complete for produced results | metadata config snapshots, config hashes, sample-level JSONL | Stronger than early stage; still needs a standard "official run checklist". |

## 4. Current Official Results

### 4.1 Retrieval: LoTTE

Source: `eval/outputs/reports/retrieval_metrics.csv`

| Variant | Samples | Recall@5 | Recall@10 | MRR@10 | NDCG@10 | Avg latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `dense_only` | 100 | 0.95 | 0.95 | 0.87999999 | 0.59717849 | 159.2473ms |
| `sparse_only` | 100 | 0.76 | 0.76 | 0.66283332 | 0.40853576 | 27.8256ms |
| `hybrid_rrf` | 100 | 0.85 | 0.85 | 0.799 | 0.51306867 | 107.0143ms |
| `hybrid_rrf_rerank` | 100 | 0.97 | 0.97 | 0.9445 | 0.67352129 | 1334.6923ms |

Interpretation:

- The strongest quality variant is `hybrid_rrf_rerank`.
- `hybrid_rrf` alone underperforms `dense_only` in this current 100-sample setting, so the benefit is mainly from rerank, not from RRF alone.
- `sparse_only` is fastest but materially worse on quality.
- The rerank latency cost is large and should be explicitly reported. This is not a free quality gain.

### 4.2 RAGBench End-To-End

Source: `eval/outputs/reports/rag_metrics.csv`

| Dataset | Variant | Samples | Answer accuracy | Groundedness | Avg generation latency |
| --- | --- | ---: | ---: | ---: | ---: |
| `ragbench` / techqa | `grounded_answer` | 50 | 0.31859484 | 0.8 | 91777.4782ms |
| `ragbench` / techqa | `grounded_answer_no_rewrite` | 50 | 0.32992028 | 0.88 | 67263.7726ms |
| `ragbench_hotpotqa` | `grounded_answer_no_rewrite_hotpotqa` | 50 | 0.46392434 | 0.98 | 27848.4834ms |
| `ragbench_emanual` | `grounded_answer_no_rewrite_emanual` | 50 | 0.3838223 | 1.0 | 26691.332ms |

Interpretation:

- `no-rewrite` should be the default baseline for the next expansion round.
- Current groundedness is high on `hotpotqa` and `emanual`, while answer accuracy is still moderate. This points to answer extraction and synthesis quality as a bigger bottleneck than hallucination.
- `techqa` remains slower than the other subsets and deserves a sample-level latency and error analysis pass.

### 4.3 Reviewed Custom Rewrite Matrix

Source: `eval/outputs/reports/rewrite_metrics.csv`

| Variant | Samples | Supported | Answer accuracy | Groundedness | Avg generation latency | Trigger rate | Retrieval stages |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `no_rewrite` | 40 | 40 | 0.05951734 | 1.0 | 46885.81975ms | 0.0 | `initial=40` |
| `always_step_back` | 40 | 40 | 0.0600714 | 1.0 | 55428.805ms | 1.0 | `expanded=40` |
| `always_hyde` | 40 | 40 | 0.06117123 | 1.0 | 51538.9455ms | 1.0 | `expanded=40` |
| `dynamic_rewrite` | 40 | 40 | 0.06553643 | 1.0 | 59629.152ms | 0.275 | `expanded=11`, `initial=29` |

Interpretation:

- All four official rewrite variants completed with `supported_sample_count=40/40` and no sample-level runner errors.
- `dynamic_rewrite` is currently the best quality variant on this reviewed custom matrix, but the gain over no-rewrite is small in absolute terms: `0.06553643` vs `0.05951734`.
- `dynamic_rewrite` triggered rewrite on `11/40` samples, all via Step-Back, so current auto mode is conservative and does not select HyDE.
- Forced rewrite adds latency. Compared with no-rewrite at about `46.9s`, Step-Back is about `55.4s`, HyDE is about `51.5s`, and dynamic rewrite is about `59.6s`.
- Groundedness is `1.0` across variants, so the main decision is quality delta versus latency and trigger precision, not hallucination reduction.
- Because 5 no-answer rows have null answer-accuracy by design, sample-level subset analysis is needed before writing a strong external claim.

### 4.4 Latency And Observability

Source: `eval/outputs/reports/latency_metrics.csv`

| Mode | Samples | Mean duration | P95 duration | Mean first event | Mean first token | Trace coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `sync` | 10 | 25534.4599ms | 62439.0609ms | N/A | N/A | 0.3 |
| `stream` | 3 | 51621.2514ms | 60590.7203ms | 2754.4919ms | 50172.5146ms | 1.0 |

Interpretation:

- Streaming provides early intermediate visibility, with first event around `2.75s` in the latest official run.
- First answer token is still late, around `50.17s` in the current 3-sample stream run.
- Because `sync` has 10 samples and `stream` has 3 samples, this is a baseline, not a final comparison.
- The trace coverage improvement after disabling internet search is a meaningful engineering win, but it needs a balanced rerun.

## 5. Key Engineering Progress

The project has solved several issues that directly affected evaluation trustworthiness:

- Official mode no longer silently falls back to mock Milvus.
- BM25 state is synchronized with vector-store corpus changes.
- `rag_trace` now includes enough fields for request, retrieval, rewrite, and timing analysis.
- RAGBench now uses subset-specific aligned collections instead of accidentally querying LoTTE corpus.
- Long-running jobs use heartbeat monitoring and fail-fast log scanning.
- Internet search is disabled in official evaluation to avoid external-network noise.
- Embedding provider compatibility issues were worked through, and the current formal embedding path uses `Pro/BAAI/bge-m3` with 1024-dimensional vectors.

These items are documented in `eval/EVAL_PROBLEM_ANALYSIS.md` and `eval/ISSUE_TRACKER.md`.

## 6. Main Risks And Gaps

### 6.1 The custom dataset is usable internally but still needs external spot-checking

`eval/datasets/custom/custom_eval.jsonl` has been promoted to 40 AI-assisted reviewed rows. `eval/scripts/validate_custom_eval.py` now requires explicit `annotation_status=reviewed`, and the latest report at `eval/datasets/custom/custom_eval_validation.json` shows `valid_sample_count=40` and `is_formal_benchmark_ready=true`.

This unblocks internal official runs for:

- cross-chunk answer accuracy
- context completeness
- no-answer refusal correctness
- rewrite-needed subset evaluation
- auto-merging claims

To reduce the manual annotation workload, `eval/scripts/build_custom_annotation_draft.py` extracts candidate evidence spans from local PDFs and writes `eval/datasets/custom/custom_eval_annotation_draft.jsonl`. `promote_silver_to_reviewed_custom_eval.py` has now produced `custom_eval.jsonl` from the reviewed silver evidence rows.

For pipeline debugging only, `eval/scripts/build_custom_silver_eval.py` writes `eval/datasets/custom/custom_eval_silver.jsonl`. The latest silver validation has `sample_count=40`, `valid_sample_count=40`, but `is_formal_benchmark_ready=false` because every row is `annotation_status=silver_generated`.

### 6.2 Chunking metrics are missing; rewrite now needs interpretation

The task list explicitly asks for chunking / auto-merging and rewrite experiments. Current status:

- `eval/outputs/reports/chunking_metrics.csv` is still empty.
- `eval/outputs/reports/rewrite_metrics.csv` is now populated by the reviewed custom official matrix.

The existing RAGBench rewrite comparison is useful context, and the reviewed custom matrix now gives a direct Step-Back / HyDE / dynamic rewrite comparison.

Current matrix readiness:

- Chunking configs added:
  - `eval/configs/chunking_fixed_official.yaml`
  - `eval/configs/chunking_multi_level_official.yaml`
  - `eval/configs/chunking_auto_merge_official.yaml`
- Rewrite configs added:
  - `eval/configs/rewrite_no_rewrite_official.yaml`
  - `eval/configs/rewrite_step_back_official.yaml`
  - `eval/configs/rewrite_hyde_official.yaml`
  - `eval/configs/rewrite_dynamic_official.yaml`
- Runtime control fixed:
  - `run_rag_eval.py` now applies `rewrite_mode`, `auto_merge_enabled`, `auto_merge_threshold`, and `leaf_retrieve_level` from config params before importing the backend RAG graph.
  - `rag_pipeline.py` now supports forced rewrite modes for Step-Back and HyDE comparison variants.
- Smoke hygiene fixed:
  - `aggregate_results.py` skips `*_smoke`, `smoke`, and `not_official` outputs by default.
  - `--include-smoke` can be used when debugging.
- Official rewrite matrix completed:
  - `no_rewrite`: `sample_count=40`, `answer_accuracy=0.05951734`, `rewrite_trigger_rate=0.0`
  - `always_step_back`: `sample_count=40`, `answer_accuracy=0.0600714`, `rewrite_trigger_rate=1.0`
  - `always_hyde`: `sample_count=40`, `answer_accuracy=0.06117123`, `rewrite_trigger_rate=1.0`
  - `dynamic_rewrite`: `sample_count=40`, `answer_accuracy=0.06553643`, `rewrite_trigger_rate=0.275`

Silver smoke result:

- `embeddings_custom_silver_smoke` now includes:
  - `attention-is-all-you-need-Paper.pdf`: `leaf=53`
  - `19cf00420ca_cc2.pdf`: `leaf=140`
- `rewrite_silver_no_rewrite_smoke` on `custom_eval_silver_smoke_mixed5.jsonl` produced `supported_sample_count=5/5`.
- `rewrite_silver_dynamic_smoke` on `custom_eval_silver_smoke_rewrite1.jsonl` produced `supported_sample_count=1/1`.
- The dynamic rewrite trace confirms `rewrite_mode=auto`, `rewrite_needed=true`, `rewrite_strategy=step_back`, and `retrieval_stage=expanded`.
- After setting `MILVUS_COLLECTION=embeddings_custom_silver_smoke`, retrieval came from the expected custom/silver collection instead of LoTTE.
- The smoke answer accuracy remains low, which is acceptable for silver smoke; it is not an official metric and mainly validates runner wiring, environment injection, collection isolation, and trace output.

Reviewed custom official collection:

- `MILVUS_COLLECTION=embeddings_custom_official`
- Ingested with `--skip-parent-store`:
  - `attention-is-all-you-need-Paper.pdf`: `leaf=53`
  - `19cf00420ca_cc2.pdf`: `leaf=140`
- This is enough to start reviewed custom rewrite experiments.
- It is not enough for strict auto-merging claims, because parent chunks were not written due to the current SQLite parent store limitation.

### 6.3 Resume export is usable only for completed metric families

`eval/outputs/reports/resume_bullets.md` has been regenerated from the latest `results_table.csv`. It is usable for retrieval, RAGBench, and latency claims, but it intentionally marks chunking / auto-merging and formal rewrite-matrix metrics as pending.

### 6.4 The current best retrieval variant has a latency tradeoff

`hybrid_rrf_rerank` is best for Recall/MRR but costs about `1335ms` average retrieval latency, much higher than `dense_only` at about `159ms`. The final narrative should frame this as a quality-latency tradeoff, not a universal improvement.

### 6.5 Some status text is stale

The beginning of `eval/ISSUE_TRACKER.md` still says formal retrieval/RAG results were not yet complete, while later entries and reports show they are now available. This document should be treated as a process log, not the current source of truth.

## 7. Recommended Next Plan

### P0: Make existing official results report-ready

Goal: turn the current retrieval / RAG / latency outputs into a trustworthy interim report.

Actions:

1. Done: fix `export_resume_bullets.py` so it reads current `results_table.csv` / metric CSVs and no longer emits `N/A`.
2. Done: rerun `aggregate_results.py` and `export_resume_bullets.py`.
3. Done: update `eval/README.md` to clearly mark which results are official and which are still pending.
4. Done: normalize stale text in `ISSUE_TRACKER.md` so the opening status does not contradict later evidence.
5. Done: add an "official run checklist" covering readiness check, generation smoke, heartbeat wrapper, config hash, records, metadata, and aggregation.

Expected output:

- Updated `results_summary.md`
- Corrected `resume_bullets.md`
- A short interim report that can safely cite LoTTE and RAGBench numbers

### P1: Build the real custom benchmark

Goal: unblock chunking, rewrite, refusal, and project-specific claims.

Actions:

1. Done: expand `custom_eval.jsonl` to 40 reviewed samples.
2. Done: fill `gold_answer`, `gold_spans`, `gold_doc_ids`, `question_type`, `needs_parent_context`, `needs_rewrite`, and `is_unanswerable`.
3. Done: run `python eval/scripts/validate_custom_eval.py --fail-on-invalid`.
4. Done: create a dedicated reviewed-custom official Milvus collection.
5. Done: create `embeddings_custom_official` and ingest reviewed custom source documents as leaf chunks.
6. Done: run reviewed custom rewrite pilots on no-rewrite, dynamic, Step-Back, and HyDE paths.
7. Done: add `eval/scripts/run_custom_rewrite_official_matrix.ps1` for the full official rewrite matrix.
8. Done: run rewrite official matrix on reviewed custom eval with heartbeat and long timeout.
9. Next: analyze rewrite sample-level records by question type and trigger correctness.
10. Next: restore writable parent store before strict auto-merging / chunking official matrix.
11. Continue to use silver smoke only for runner debugging; do not copy silver metrics into the final report.

Expected output:

- Formal `eval/datasets/custom/custom_eval.jsonl`
- Non-empty custom manifest with reviewed label counts
- Basis for `Cross-chunk answer accuracy`, `Context completeness`, and `Refusal correctness`

### P2: Run chunking / auto-merging experiments

Goal: produce the missing task-list numbers for long-document behavior.

Actions:

1. Restore or isolate a writable parent chunk store.
2. Run the matrix:
   - `fixed_chunk`
   - `multi_level`
   - `auto_merge`
3. Evaluate on custom cross-chunk samples first, then optionally on RAGBench long-context samples.
4. Write sample-level records and aggregate `chunking_metrics.csv`.

Expected output:

- `eval/outputs/chunking/*/records.jsonl`
- non-empty `eval/outputs/reports/chunking_metrics.csv`
- answerable statement on whether auto-merging improves context completeness

### P3: Analyze the formal rewrite matrix

Goal: move from raw matrix metrics to an evidence-based rewrite recommendation.

Actions:

1. Done: prepare rewrite-needed samples from custom eval.
2. Done: run:
   - `no_rewrite`
   - `always_step_back`
   - `always_hyde`
   - `dynamic_rewrite`
3. Next: analyze `rewrite_trigger_rate`, trigger correctness, quality deltas, and added latency by question type.
4. Keep `no-rewrite` as the default production baseline until the dynamic gain is shown to be worth the added latency.

Expected output:

- non-empty `eval/outputs/reports/rewrite_metrics.csv`
- evidence-based recommendation on when rewrite should trigger

### P4: Stabilize and expand latency evaluation

Goal: make SSE claims robust.

Actions:

1. Rerun `sync` and `stream` with the same sample count, ideally 20 to 30 samples.
2. Repeat each sample 3 to 5 times if budget allows.
3. Report `TTFT`, `TTFM`, end-to-end latency, P95 latency, trace coverage, and stage timing breakdown.
4. Separate "first intermediate event" from "first answer token" in all summaries.

Expected output:

- balanced latency comparison
- defensible tracing and user-experience claims

### P5: Expand official retrieval and RAG scale

Goal: move from promising official baselines to stronger benchmark coverage.

Actions:

1. Expand LoTTE beyond technology-domain 100 samples to science and writing, matching the task-list requirement.
2. Increase RAGBench subsets from 50 to 100+ samples after generation gateway smoke passes.
3. Continue using dedicated Milvus collections per dataset/subset.
4. Keep external service smoke checks before long runs.

Expected output:

- broader retrieval table by domain
- stronger end-to-end RAG benchmark table

## 8. Suggested Near-Term Order

The best order is:

1. Fix report/export correctness first, because existing numbers are already useful.
2. Build the reviewed custom benchmark, because it unlocks the missing task-list metrics.
3. Run chunking experiments before the full rewrite matrix, because chunking depends on data and store correctness rather than generation policy.
4. Rerun balanced latency after disabling external-search noise, because the current stream/sync sample mismatch weakens comparison.
5. Expand LoTTE/RAGBench scale once the reporting pipeline is clean.

## 9. Current Definition-Of-Done Status

| DoD item from task list | Status |
| --- | --- |
| Download and process LoTTE | Partially done. Three domains are present, but official metrics currently cover technology subset. |
| Download and process RAGBench | Partially done. Three 50-sample subsets are present and evaluated. |
| Build custom dataset | Done for internal official runs. 40 AI-assisted reviewed rows pass validation. |
| Complete retrieval eval | Partially done. Official technology 100-sample matrix exists. |
| Complete chunking eval | Not done. Metrics are empty. |
| Complete rewrite eval | Partially done. RAGBench auto-vs-off evidence exists, but no formal rewrite matrix. |
| Complete RAG eval | Partially done. Three official 50-sample subsets exist. |
| Complete latency eval | Partially done. Baselines exist, but need balanced sample counts. |
| Output sample-level JSONL and summary CSVs | Done for retrieval/RAG/latency; not done for chunking/rewrite. |
| Generate `results_summary.md` | Done. |
| Generate `resume_bullets.md` | Done for retrieval/RAGBench/latency claims; chunking/rewrite claims remain pending. |
| README explains reproduction | Partially done. Needs current-status and official-run checklist updates. |
| Produce resume-ready quantified claims | Partially done. Retrieval and RAG claims are usable; chunking/rewrite claims are not yet usable. |

## 10. Bottom Line

The project is no longer in a "just scaffolding" phase. It has credible official retrieval, RAG, and latency outputs with metadata and sample-level records.

The next milestone should not be "run more scripts" in the abstract. It should be:

1. make the current report/export layer consistent,
2. build a real custom benchmark,
3. fill the missing chunking and rewrite metric tables,
4. then scale the official benchmark runs.

Until those are done, the safest public-facing claim is around LoTTE retrieval quality and the RAGBench no-rewrite baseline. Claims about auto-merging, cross-chunk accuracy, dynamic rewrite improvement, and refusal correctness should remain explicitly marked as pending.
