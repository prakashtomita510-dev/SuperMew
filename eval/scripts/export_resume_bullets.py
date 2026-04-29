from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path


def _load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _to_decimal(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _format_decimal(value: str | None, places: int = 3) -> str:
    parsed = _to_decimal(value)
    if parsed is None:
        return "N/A"
    quantized = parsed.quantize(Decimal("1." + ("0" * places)))
    return str(quantized.normalize())


def _format_ms(value: str | None) -> str:
    parsed = _to_decimal(value)
    if parsed is None:
        return "N/A"
    return str(parsed.quantize(Decimal("1")))


def _find_row(rows: list[dict[str, str]], kind: str, variant: str, dataset: str | None = None) -> dict[str, str] | None:
    for row in rows:
        if row.get("kind") != kind or row.get("variant") != variant:
            continue
        if dataset is not None and row.get("dataset") != dataset:
            continue
        return row
    return None


def _best_row(rows: list[dict[str, str]], kind: str, metric: str) -> dict[str, str] | None:
    best: tuple[Decimal, dict[str, str]] | None = None
    for row in rows:
        if row.get("kind") != kind:
            continue
        value = _to_decimal(row.get(metric))
        if value is None:
            continue
        if best is None or value > best[0]:
            best = (value, row)
    return best[1] if best else None


def _pct_delta(new_value: str | None, old_value: str | None) -> str:
    new = _to_decimal(new_value)
    old = _to_decimal(old_value)
    if new is None or old is None or old == 0:
        return "N/A"
    return str((((new - old) / old) * Decimal("100")).quantize(Decimal("1.0")).normalize())


def build_resume_bullets(rows: list[dict[str, str]]) -> str:
    dense = _find_row(rows, "retrieval", "dense_only")
    rerank = _find_row(rows, "retrieval", "hybrid_rrf_rerank")
    stream = _find_row(rows, "latency", "stream")
    best_rag = _best_row(rows, "rag", "answer_accuracy")
    grounded_rag = _best_row(rows, "rag", "groundedness_score")

    recall = _format_decimal(rerank.get("recall_at_5") if rerank else None)
    mrr = _format_decimal(rerank.get("mrr_at_10") if rerank else None)
    recall_delta = _pct_delta(
        rerank.get("recall_at_5") if rerank else None,
        dense.get("recall_at_5") if dense else None,
    )
    mrr_delta = _pct_delta(
        rerank.get("mrr_at_10") if rerank else None,
        dense.get("mrr_at_10") if dense else None,
    )
    first_event = _format_ms(stream.get("mean_time_to_first_event_ms") if stream else None)
    ttft = _format_ms(stream.get("mean_time_to_first_token_ms") if stream else None)
    trace = _format_decimal(stream.get("trace_coverage_rate") if stream else None)
    best_rag_accuracy = _format_decimal(best_rag.get("answer_accuracy") if best_rag else None)
    best_rag_dataset = best_rag.get("dataset", "N/A") if best_rag else "N/A"
    best_groundedness = _format_decimal(grounded_rag.get("groundedness_score") if grounded_rag else None)
    groundedness_dataset = grounded_rag.get("dataset", "N/A") if grounded_rag else "N/A"

    return (
        "# Resume Bullets\n\n"
        "> Note: Current resume-ready numbers cover retrieval, RAGBench, and latency. Chunking / auto-merging and formal rewrite-matrix metrics are still pending and should not be claimed yet.\n\n"
        "## Version A\n\n"
        f"- 基于 LoTTE 与 RAGBench 搭建 RAG 离线量化评测流水线，统一配置快照、样本级 JSONL、聚合 CSV 与问题台账；在 LoTTE official 100 样本上，hybrid retrieval + RRF + rerank 达到 Recall@5={recall}、MRR@10={mrr}，相对 dense-only 分别提升 {recall_delta}% 和 {mrr_delta}%。\n"
        f"- 完成 RAGBench techqa / hotpotqa / emanual 端到端正式基线评测，当前最佳 answer accuracy={best_rag_accuracy}（{best_rag_dataset}），最高 groundedness={best_groundedness}（{groundedness_dataset}）；并完成 SSE 可观测链路基线，首个中间事件平均 {first_event}ms 到达，stream trace coverage={trace}。\n\n"
        "## Version B\n\n"
        f"- 面向 Agent + 多级混合检索 RAG 系统构建评测驱动优化框架，覆盖 retrieval、RAG answer quality、groundedness、SSE latency 与 trace coverage；当前已沉淀 Recall@5={recall}、MRR@10={mrr}、Answer Accuracy={best_rag_accuracy}、Groundedness={best_groundedness}、TTFT={ttft}ms 等核心指标的可追溯报告。\n"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate resume-ready bullets from aggregated eval results.")
    parser.add_argument("--results-table", type=Path, default=Path("eval/outputs/reports/results_table.csv"))
    parser.add_argument("--output", type=Path, default=Path("eval/outputs/reports/resume_bullets.md"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = _load_rows(args.results_table)
    text = build_resume_bullets(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"wrote resume bullets to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
