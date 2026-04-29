from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("eval/datasets/custom/custom_eval_silver.jsonl")
DEFAULT_OUTPUT = Path("eval/datasets/custom/custom_eval_silver_smoke_mixed5.jsonl")
DEFAULT_MANIFEST = Path("eval/datasets/custom/custom_eval_silver_smoke_mixed5.manifest.json")
DEFAULT_TARGETS = {
    "direct_fact": 1,
    "cross_chunk": 1,
    "rewrite_needed": 1,
    "ambiguous": 1,
    "no_answer": 1,
}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_subset(rows: list[dict[str, Any]], targets: dict[str, int]) -> list[dict[str, Any]]:
    counts = Counter()
    selected = []
    for row in rows:
        question_type = str(row.get("question_type") or "")
        if counts[question_type] >= targets.get(question_type, 0):
            continue
        selected.append(row)
        counts[question_type] += 1
        if all(counts[key] >= value for key, value in targets.items()):
            break
    return selected


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a small mixed silver smoke subset.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Override target counts as question_type=count. Can be repeated.",
    )
    return parser.parse_args(argv)


def _parse_targets(items: list[str]) -> dict[str, int]:
    if not items:
        return DEFAULT_TARGETS
    targets: dict[str, int] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid target {item!r}; expected question_type=count")
        key, value = item.split("=", 1)
        targets[key.strip()] = int(value)
    return targets


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = _load_jsonl(args.input)
    targets = _parse_targets(args.target)
    subset = build_subset(rows, targets)
    _write_jsonl(args.output, subset)
    _write_json(
        args.manifest,
        {
            "source": str(args.input),
            "output": str(args.output),
            "sample_count": len(subset),
            "question_type_counts": dict(Counter(row["question_type"] for row in subset)),
            "targets": targets,
            "status": "silver_smoke_not_official",
        },
    )
    print(f"wrote {len(subset)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
