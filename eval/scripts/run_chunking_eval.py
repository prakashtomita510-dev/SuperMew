from __future__ import annotations

import argparse
import json
from pathlib import Path

from config import EvalConfig, load_config_file
from run_rag_eval import run_eval as run_rag_eval
from results import ResultBundleWriter


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run chunking-focused eval using the normalized RAG eval runner.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset-path", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = EvalConfig.from_mapping(load_config_file(args.config))
    rows, summary = run_rag_eval(config, args.dataset_path)
    writer = ResultBundleWriter(Path(config.output_dir))
    writer.write(
        prefix=config.variant,
        records=rows,
        metadata={"config": config.snapshot(), "summary": summary},
        summary="# Chunking Eval\n\nGenerated chunking-focused answer metrics.\n",
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
