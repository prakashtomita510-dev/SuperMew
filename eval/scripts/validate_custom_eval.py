from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "id",
    "question",
    "gold_answer",
    "gold_doc_ids",
    "gold_spans",
    "question_type",
    "needs_parent_context",
    "needs_rewrite",
    "is_unanswerable",
}

ALLOWED_QUESTION_TYPES = {
    "direct_fact",
    "cross_chunk",
    "rewrite_needed",
    "ambiguous",
    "no_answer",
}

TODO_MARKERS = ("TODO", "placeholder", "replace with")
FORMAL_ANNOTATION_STATUS = "reviewed"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} is not valid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number} must contain a JSON object")
            row["_line_number"] = line_number
            rows.append(row)
    return rows


def _has_todo(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in TODO_MARKERS)


def _validate_row(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(field for field in REQUIRED_FIELDS if field not in row)
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")

    if not str(row.get("id") or "").strip():
        errors.append("id is empty")
    if not str(row.get("question") or "").strip() or _has_todo(row.get("question")):
        errors.append("question is empty or still TODO")
    if not row.get("is_unanswerable") and (
        not str(row.get("gold_answer") or "").strip() or _has_todo(row.get("gold_answer"))
    ):
        errors.append("gold_answer is empty or still TODO")

    gold_doc_ids = row.get("gold_doc_ids")
    if not isinstance(gold_doc_ids, list) or not gold_doc_ids:
        errors.append("gold_doc_ids must be a non-empty list")

    gold_spans = row.get("gold_spans")
    if not row.get("is_unanswerable") and (not isinstance(gold_spans, list) or not gold_spans):
        errors.append("answerable samples require at least one gold_span")

    question_type = row.get("question_type")
    if question_type not in ALLOWED_QUESTION_TYPES:
        errors.append(
            "question_type must be one of: " + ", ".join(sorted(ALLOWED_QUESTION_TYPES))
        )

    for boolean_field in ("needs_parent_context", "needs_rewrite", "is_unanswerable"):
        if boolean_field in row and not isinstance(row.get(boolean_field), bool):
            errors.append(f"{boolean_field} must be boolean")

    if row.get("question_type") == "cross_chunk" and not row.get("needs_parent_context"):
        errors.append("cross_chunk samples should set needs_parent_context=true")
    if row.get("question_type") == "rewrite_needed" and not row.get("needs_rewrite"):
        errors.append("rewrite_needed samples should set needs_rewrite=true")
    if row.get("question_type") == "no_answer" and not row.get("is_unanswerable"):
        errors.append("no_answer samples should set is_unanswerable=true")

    return errors


def validate(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = _load_jsonl(path)
    row_errors = []
    question_types = Counter()
    annotation_statuses = Counter()
    for row in rows:
        question_type = str(row.get("question_type") or "")
        if question_type:
            question_types[question_type] += 1
        annotation_status = str(row.get("annotation_status") or "")
        if annotation_status:
            annotation_statuses[annotation_status] += 1
        errors = _validate_row(row)
        if errors:
            row_errors.append(
                {
                    "line": row.get("_line_number"),
                    "id": row.get("id"),
                    "errors": errors,
                }
            )

    all_reviewed = bool(rows) and all(
        str(row.get("annotation_status") or "") == FORMAL_ANNOTATION_STATUS
        for row in rows
    )
    summary = {
        "dataset_path": str(path),
        "sample_count": len(rows),
        "valid_sample_count": len(rows) - len(row_errors),
        "invalid_sample_count": len(row_errors),
        "question_type_counts": dict(sorted(question_types.items())),
        "annotation_status_counts": dict(sorted(annotation_statuses.items())),
        "all_samples_reviewed": all_reviewed,
        "is_formal_benchmark_ready": len(rows) >= 40 and not row_errors and all_reviewed,
        "minimum_formal_sample_count": 40,
    }
    return row_errors, summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate custom eval annotations before official eval.")
    parser.add_argument("--dataset-path", type=Path, default=Path("eval/datasets/custom/custom_eval.jsonl"))
    parser.add_argument("--report-path", type=Path, default=Path("eval/datasets/custom/custom_eval_validation.json"))
    parser.add_argument("--fail-on-invalid", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    row_errors, summary = validate(args.dataset_path)
    report = {
        "summary": summary,
        "row_errors": row_errors,
    }
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if row_errors:
        print(f"wrote validation details to {args.report_path}")
    if args.fail_on_invalid and not summary["is_formal_benchmark_ready"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
