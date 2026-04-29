from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from config import EvalConfig, load_config_file
from run_rag_eval import run_eval as run_rag_eval
from results import ResultBundleWriter


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _enrich_rewrite_summary(rows: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    trigger_count = 0
    strategy_counts: Counter[str] = Counter()
    stage_counts: Counter[str] = Counter()
    rewrite_timings = []
    retrieve_timings = []
    generate_timings = []

    for row in rows:
        trace = row.get("rag_trace") or {}
        if trace.get("rewrite_needed"):
            trigger_count += 1

        strategy = trace.get("rewrite_strategy")
        if strategy:
            strategy_counts[str(strategy)] += 1

        stage = trace.get("retrieval_stage")
        if stage:
            stage_counts[str(stage)] += 1

        timings = trace.get("stage_timings_ms") or {}
        for key, target in (
            ("rewrite_ms", rewrite_timings),
            ("retrieve_ms", retrieve_timings),
            ("generate_ms", generate_timings),
        ):
            value = timings.get(key)
            if isinstance(value, (int, float)):
                target.append(float(value))

    sample_count = len(rows)
    enriched = dict(summary)
    enriched.update(
        {
            "rewrite_trigger_count": trigger_count,
            "rewrite_trigger_rate": round(trigger_count / sample_count, 6) if sample_count else None,
            "rewrite_strategy_counts": dict(sorted(strategy_counts.items())),
            "retrieval_stage_counts": dict(sorted(stage_counts.items())),
            "avg_rewrite_stage_ms": _mean(rewrite_timings),
            "avg_retrieve_stage_ms": _mean(retrieve_timings),
            "avg_generate_stage_ms": _mean(generate_timings),
        }
    )
    return enriched


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run rewrite-focused eval using the normalized RAG eval runner.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset-path", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = EvalConfig.from_mapping(load_config_file(args.config))
    rows, summary = run_rag_eval(config, args.dataset_path)
    summary = _enrich_rewrite_summary(rows, summary)
    writer = ResultBundleWriter(Path(config.output_dir))
    writer.write(
        prefix=config.variant,
        records=rows,
        metadata={"config": config.snapshot(), "summary": summary},
        summary="# Rewrite Eval\n\nGenerated rewrite-focused answer metrics.\n",
        table_columns=[
            "question_id",
            "variant",
            "answer_accuracy",
            "groundedness_score",
            "generation_latency_ms",
            "retrieval_mode",
            "vector_backend",
        ],
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
