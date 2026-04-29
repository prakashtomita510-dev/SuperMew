from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DRAFT_FILE = Path("eval/datasets/custom/custom_eval_annotation_draft.jsonl")
DEFAULT_OUTPUT_FILE = Path("eval/datasets/custom/custom_eval_silver.jsonl")
DEFAULT_MANIFEST_FILE = Path("eval/datasets/custom/custom_eval_silver.manifest.json")

SILVER_TARGETS = {
    "direct_fact": 10,
    "cross_chunk": 10,
    "rewrite_needed": 10,
    "ambiguous": 5,
    "no_answer": 5,
}


REFERENCE_MARKERS = (
    "references",
    "bibliography",
    "proceedings",
    "arxiv",
    "journal of",
    "conference on",
    "curran associates",
    "advances in neural information processing systems",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _is_usable_span(span: dict[str, Any]) -> bool:
    text = _clean_text(str(span.get("span_text") or ""))
    lowered = text.lower()
    if len(text) < 120:
        return False
    if "@" in text:
        return False
    if any(marker in lowered for marker in REFERENCE_MARKERS):
        return False
    if re.match(r"^\s*\[\d+\]", text):
        return False
    if len(re.findall(r"\[\d+\]", text)) >= 2:
        return False
    return True


def _short_answer(spans: list[dict[str, Any]], max_chars: int = 360) -> str:
    parts = [_clean_text(str(span.get("span_text") or "")) for span in spans]
    answer = " ".join(part for part in parts if part)
    return answer[:max_chars].strip()


def _doc_label(doc_id: str) -> str:
    stem = Path(doc_id).stem
    if stem == "attention-is-all-you-need-Paper":
        return "Transformer paper"
    if stem == "19cf00420ca_cc2":
        return "Blood on the Clocktower rules document"
    return stem


def _make_question(row: dict[str, Any], spans: list[dict[str, Any]]) -> str:
    question_type = row["question_type"]
    first = spans[0]
    label = _doc_label(str(first.get("doc_id") or "document"))
    page = first.get("page_number", "unknown")
    if question_type == "direct_fact":
        return f"According to the {label}, what key point is stated on page {page}?"
    if question_type == "cross_chunk":
        return f"Using the provided evidence from the {label}, what two related points should be combined?"
    if question_type == "rewrite_needed":
        return f"For the {label}, explain the mechanism hinted at by the evidence on page {page}."
    if question_type == "ambiguous":
        return f"In the {label}, what does the referenced passage mean in this context?"
    if question_type == "no_answer":
        return f"According to the {label}, what is the official SuperMew production incident ID for April 2099?"
    return f"According to the {label}, what does the evidence say?"


def build_silver_rows(draft_rows: list[dict[str, Any]], max_samples: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    silver_rows: list[dict[str, Any]] = []
    skipped = Counter()
    selected_counts = Counter()

    for draft in draft_rows:
        if len(silver_rows) >= max_samples:
            break
        question_type = draft.get("question_type")
        target_count = SILVER_TARGETS.get(str(question_type), 0)
        if target_count <= 0 or selected_counts[str(question_type)] >= target_count:
            continue
        evidence = list(draft.get("evidence_preview") or draft.get("gold_spans") or [])
        usable_spans = [span for span in evidence if _is_usable_span(span)]
        if question_type == "no_answer":
            usable_spans = []
        elif not usable_spans:
            skipped[str(question_type)] += 1
            continue
        elif question_type == "cross_chunk" and len(usable_spans) < 2:
            skipped[str(question_type)] += 1
            continue

        gold_doc_ids = sorted(
            {
                str(span.get("doc_id"))
                for span in (usable_spans or evidence)
                if span.get("doc_id")
            }
        )
        if not gold_doc_ids:
            gold_doc_ids = list(draft.get("gold_doc_ids") or [])
        if not gold_doc_ids:
            skipped[str(question_type)] += 1
            continue

        is_unanswerable = question_type == "no_answer"
        row = {
            "id": f"custom-silver-{len(silver_rows) + 1:04d}",
            "question": _make_question(draft, usable_spans or evidence),
            "gold_answer": "" if is_unanswerable else _short_answer(usable_spans),
            "gold_doc_ids": gold_doc_ids,
            "gold_spans": [] if is_unanswerable else usable_spans,
            "question_type": question_type,
            "needs_parent_context": bool(draft.get("needs_parent_context")),
            "needs_rewrite": bool(draft.get("needs_rewrite")),
            "is_unanswerable": is_unanswerable,
            "source_notes": "silver generated from extracted evidence for pipeline smoke only; not manually reviewed",
            "annotation_status": "silver_generated",
        }
        silver_rows.append(row)
        selected_counts[str(question_type)] += 1

    manifest = {
        "created_at": _utc_now(),
        "status": "silver_generated_not_official",
        "sample_count": len(silver_rows),
        "question_type_counts": dict(Counter(row["question_type"] for row in silver_rows)),
        "question_type_targets": SILVER_TARGETS,
        "skipped_counts": dict(skipped),
        "notes": [
            "This dataset is for runner smoke tests and pipeline debugging only.",
            "It must not be used for official metrics or resume claims.",
            "The formal validator will not mark it as benchmark-ready because annotation_status is silver_generated.",
        ],
    }
    return silver_rows, manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a silver custom eval set for non-official smoke tests.")
    parser.add_argument("--draft-file", type=Path, default=DEFAULT_DRAFT_FILE)
    parser.add_argument("--output-file", type=Path, default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--manifest-file", type=Path, default=DEFAULT_MANIFEST_FILE)
    parser.add_argument("--max-samples", type=int, default=40)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    draft_rows = _load_jsonl(args.draft_file)
    silver_rows, manifest = build_silver_rows(draft_rows, max_samples=args.max_samples)
    _write_jsonl(args.output_file, silver_rows)
    _write_json(args.manifest_file, manifest)
    print(f"wrote {len(silver_rows)} silver rows to {args.output_file}")
    print(f"wrote manifest to {args.manifest_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
