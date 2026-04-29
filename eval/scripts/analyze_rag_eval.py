from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _safe_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _stage_value(row: dict[str, Any], key: str) -> float | None:
    trace = row.get("rag_trace") or {}
    stage = trace.get("stage_timings_ms") or {}
    return _safe_number(stage.get(key))


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    answer_scores = [_safe_number(row.get("answer_accuracy")) for row in rows]
    answer_scores = [item for item in answer_scores if item is not None]
    latencies = [_safe_number(row.get("generation_latency_ms")) for row in rows]
    latencies = [item for item in latencies if item is not None]

    rewrite_count = sum(1 for row in rows if (row.get("rag_trace") or {}).get("rewrite_needed"))
    route_counts = Counter((row.get("rag_trace") or {}).get("grade_route") or "none" for row in rows)
    hallucination_counts = Counter((row.get("rag_trace") or {}).get("hallucination_score") or "none" for row in rows)
    grade_counts = Counter((row.get("rag_trace") or {}).get("grade_score") or "none" for row in rows)

    lowest_accuracy = sorted(
        rows,
        key=lambda row: (_safe_number(row.get("answer_accuracy")) is None, _safe_number(row.get("answer_accuracy")) or 10.0),
    )[:10]
    highest_latency = sorted(
        rows,
        key=lambda row: _safe_number(row.get("generation_latency_ms")) or -1.0,
        reverse=True,
    )[:10]

    stage_keys = ("rewrite_ms", "retrieve_initial_ms", "retrieve_expanded_ms", "retrieve_ms", "generate_ms")
    stage_summary: dict[str, float] = {}
    for key in stage_keys:
        values = [_stage_value(row, key) for row in rows]
        values = [item for item in values if item is not None]
        if values:
            stage_summary[key] = round(mean(values), 2)

    return {
        "sample_count": len(rows),
        "answer_accuracy_mean": round(mean(answer_scores), 6) if answer_scores else None,
        "answer_accuracy_min": round(min(answer_scores), 6) if answer_scores else None,
        "answer_accuracy_max": round(max(answer_scores), 6) if answer_scores else None,
        "generation_latency_mean_ms": round(mean(latencies), 2) if latencies else None,
        "generation_latency_p50_ms": round(median(latencies), 2) if latencies else None,
        "rewrite_needed_count": rewrite_count,
        "rewrite_needed_rate": round(rewrite_count / len(rows), 4) if rows else 0.0,
        "grade_routes": dict(route_counts),
        "grade_scores": dict(grade_counts),
        "hallucination_scores": dict(hallucination_counts),
        "stage_mean_ms": stage_summary,
        "lowest_accuracy_samples": [
            {
                "question_id": row.get("question_id"),
                "answer_accuracy": _safe_number(row.get("answer_accuracy")),
                "groundedness_score": _safe_number(row.get("groundedness_score")),
                "generation_latency_ms": _safe_number(row.get("generation_latency_ms")),
                "grade_score": (row.get("rag_trace") or {}).get("grade_score"),
                "hallucination_score": (row.get("rag_trace") or {}).get("hallucination_score"),
                "rewrite_needed": bool((row.get("rag_trace") or {}).get("rewrite_needed")),
                "query": str((row.get("rag_trace") or {}).get("query") or "")[:180],
                "top_filenames": [item.get("filename") for item in ((row.get("rag_trace") or {}).get("retrieved_chunks") or [])[:3]],
            }
            for row in lowest_accuracy
        ],
        "highest_latency_samples": [
            {
                "question_id": row.get("question_id"),
                "generation_latency_ms": _safe_number(row.get("generation_latency_ms")),
                "answer_accuracy": _safe_number(row.get("answer_accuracy")),
                "rewrite_needed": bool((row.get("rag_trace") or {}).get("rewrite_needed")),
                "rewrite_strategy": (row.get("rag_trace") or {}).get("rewrite_strategy"),
                "stage_timings_ms": (row.get("rag_trace") or {}).get("stage_timings_ms") or {},
                "query": str((row.get("rag_trace") or {}).get("query") or "")[:180],
            }
            for row in highest_latency
        ],
    }


def to_markdown(summary: dict[str, Any], source: Path) -> str:
    lines = [
        "# RAG Eval Analysis",
        "",
        f"Source: `{source.as_posix()}`",
        "",
        "## Summary",
        "",
        f"- Sample count: `{summary.get('sample_count')}`",
        f"- Mean answer accuracy: `{summary.get('answer_accuracy_mean')}`",
        f"- Accuracy range: `{summary.get('answer_accuracy_min')} -> {summary.get('answer_accuracy_max')}`",
        f"- Mean generation latency: `{summary.get('generation_latency_mean_ms')} ms`",
        f"- Median generation latency: `{summary.get('generation_latency_p50_ms')} ms`",
        f"- Rewrite needed count: `{summary.get('rewrite_needed_count')}`",
        f"- Rewrite needed rate: `{summary.get('rewrite_needed_rate')}`",
        "",
        "## Route Counts",
        "",
        f"- Grade routes: `{json.dumps(summary.get('grade_routes', {}), ensure_ascii=False, sort_keys=True)}`",
        f"- Grade scores: `{json.dumps(summary.get('grade_scores', {}), ensure_ascii=False, sort_keys=True)}`",
        f"- Hallucination scores: `{json.dumps(summary.get('hallucination_scores', {}), ensure_ascii=False, sort_keys=True)}`",
        "",
        "## Mean Stage Timings",
        "",
        f"- `{json.dumps(summary.get('stage_mean_ms', {}), ensure_ascii=False, sort_keys=True)}`",
        "",
        "## Lowest Accuracy Samples",
        "",
    ]
    for item in summary.get("lowest_accuracy_samples", []):
        lines.append(
            f"- `{item['question_id']}` acc=`{item['answer_accuracy']}` grounded=`{item['groundedness_score']}` "
            f"latency=`{item['generation_latency_ms']}` rewrite=`{item['rewrite_needed']}` "
            f"grade=`{item['grade_score']}` hallucination=`{item['hallucination_score']}` "
            f"top_docs=`{item['top_filenames']}`"
        )
    lines.extend(["", "## Highest Latency Samples", ""])
    for item in summary.get("highest_latency_samples", []):
        lines.append(
            f"- `{item['question_id']}` latency=`{item['generation_latency_ms']}` acc=`{item['answer_accuracy']}` "
            f"rewrite=`{item['rewrite_needed']}` strategy=`{item['rewrite_strategy']}` "
            f"stage=`{json.dumps(item['stage_timings_ms'], ensure_ascii=False, sort_keys=True)}`"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze sample-level RAG eval records.")
    parser.add_argument("--records-path", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--summary-md", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = _load_jsonl(args.records_path)
    summary = analyze(rows)
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_md.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.summary_md.write_text(to_markdown(summary, args.records_path), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
