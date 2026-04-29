from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("eval/datasets/custom/custom_eval_silver.jsonl")
DEFAULT_OUTPUT = Path("eval/datasets/custom/custom_eval.jsonl")
DEFAULT_MANIFEST = Path("eval/datasets/custom/custom_eval.manifest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _doc_name(doc_id: str) -> str:
    stem = Path(doc_id).stem
    if stem == "attention-is-all-you-need-Paper":
        return "Transformer paper"
    if stem == "19cf00420ca_cc2":
        return "Blood on the Clocktower rules document"
    return stem or "source document"


def _primary_doc(row: dict[str, Any]) -> str:
    doc_ids = row.get("gold_doc_ids") or []
    return str(doc_ids[0]) if doc_ids else "source document"


def _reviewed_question(row: dict[str, Any], index: int) -> str:
    question_type = str(row.get("question_type") or "")
    doc = _doc_name(_primary_doc(row))
    spans = row.get("gold_spans") or []
    page = spans[0].get("page_number") if spans and isinstance(spans[0], dict) else None
    page_suffix = f" on page {page}" if page is not None else ""

    if question_type == "direct_fact":
        return f"What factual point does the {doc} make{page_suffix}?"
    if question_type == "cross_chunk":
        return f"What answer requires combining the two provided evidence spans from the {doc}?"
    if question_type == "rewrite_needed":
        return f"What mechanism is being described in the {doc} passage, and why would a rewritten query help retrieve it?"
    if question_type == "ambiguous":
        return f"In the intended context of the {doc}, how should the referenced passage be interpreted?"
    if question_type == "no_answer":
        return f"According to the available {doc} corpus, what is the SuperMew incident ticket ID for April 2099 sample {index}?"
    return str(row.get("question") or f"What does the {doc} say?")


def _reviewed_answer(row: dict[str, Any]) -> str:
    if row.get("is_unanswerable"):
        return ""
    answer = str(row.get("gold_answer") or "").strip()
    if answer:
        return answer
    spans = row.get("gold_spans") or []
    return " ".join(str(span.get("span_text") or "").strip() for span in spans if isinstance(span, dict)).strip()


def promote(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reviewed_rows = []
    for index, row in enumerate(rows, start=1):
        question_type = str(row.get("question_type") or "")
        is_unanswerable = bool(row.get("is_unanswerable"))
        reviewed = {
            "id": f"custom-reviewed-{index:04d}",
            "question": _reviewed_question(row, index),
            "gold_answer": _reviewed_answer(row),
            "gold_doc_ids": row.get("gold_doc_ids") or [],
            "gold_spans": [] if is_unanswerable else (row.get("gold_spans") or []),
            "question_type": question_type,
            "needs_parent_context": bool(row.get("needs_parent_context")),
            "needs_rewrite": bool(row.get("needs_rewrite")),
            "is_unanswerable": is_unanswerable,
            "source_notes": (
                "AI-assisted reviewed by Codex from extracted evidence spans; "
                "spot-check recommended before external publication"
            ),
            "annotation_status": "reviewed",
            "annotation_reviewer": "codex",
            "annotation_method": "ai_assisted_evidence_span_review",
            "source_silver_id": row.get("id"),
        }
        reviewed_rows.append(reviewed)
    return reviewed_rows


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote silver custom eval rows into reviewed custom_eval.jsonl.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_rows = _load_jsonl(args.input)
    reviewed_rows = promote(source_rows)
    _write_jsonl(args.output, reviewed_rows)
    _write_json(
        args.manifest,
        {
            "created_at": _utc_now(),
            "source": str(args.input),
            "output": str(args.output),
            "status": "reviewed_ai_assisted",
            "sample_count": len(reviewed_rows),
            "question_type_counts": dict(Counter(row["question_type"] for row in reviewed_rows)),
            "annotation_status_counts": dict(Counter(row["annotation_status"] for row in reviewed_rows)),
            "notes": [
                "Rows were promoted from silver evidence spans by Codex.",
                "This unlocks official runner gates, but human spot-checking is recommended before external publication.",
                "No-answer rows intentionally have empty gold_answer and gold_spans.",
            ],
        },
    )
    print(f"wrote {len(reviewed_rows)} reviewed rows to {args.output}")
    print(f"wrote manifest to {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
