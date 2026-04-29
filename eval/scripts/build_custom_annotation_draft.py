from __future__ import annotations

import argparse
import json
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from pypdf import PdfReader
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "pypdf is required. Run this script with an environment that has pypdf installed, "
        "for example .venv_311\\Scripts\\python.exe on this workspace."
    ) from exc


DEFAULT_SOURCE_DIR = Path("data/documents")
DEFAULT_OUTPUT_FILE = Path("eval/datasets/custom/custom_eval_annotation_draft.jsonl")
DEFAULT_MANIFEST_FILE = Path("eval/datasets/custom/custom_eval_annotation_draft.manifest.json")

QUESTION_TYPE_TARGETS = {
    "direct_fact": 15,
    "cross_chunk": 15,
    "rewrite_needed": 10,
    "ambiguous": 5,
    "no_answer": 5,
}


@dataclass(frozen=True)
class EvidenceSpan:
    doc_id: str
    page_number: int
    span_text: str
    start_char: int
    end_char: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def _looks_usable_span(text: str) -> bool:
    lowered = text.lower()
    if "@" in text:
        return False
    reference_markers = (
        "references",
        "bibliography",
        "proceedings",
        "arxiv",
        "journal of",
        "conference on",
        "curran associates",
        "coRR".lower(),
        "advances in neural information processing systems",
    )
    if any(marker in lowered for marker in reference_markers):
        return False
    if re.search(r"\[\d+\].{0,80}\b(in|arxiv|proceedings|conference)\b", lowered):
        return False
    if re.match(r"^\s*\[\d+\]", text):
        return False
    if len(re.findall(r"\[\d+\]", text)) >= 2:
        return False
    letters = re.findall(r"[A-Za-z\u4e00-\u9fff]", text)
    return len(letters) >= 80


def _extract_pdf_spans(path: Path, min_chars: int, max_chars: int) -> list[EvidenceSpan]:
    reader = PdfReader(str(path))
    spans: list[EvidenceSpan] = []
    for page_index, page in enumerate(reader.pages):
        text = _normalize_text(page.extract_text() or "")
        if len(text) < min_chars:
            continue

        sentences = re.split(r"(?<=[.!?。！？])\s+", text)
        buffer = ""
        start_char = 0
        cursor = 0
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if not buffer:
                start_char = cursor
            candidate = f"{buffer} {sentence}".strip()
            if len(candidate) < min_chars:
                buffer = candidate
            else:
                span_text = candidate[:max_chars].strip()
                if len(span_text) >= min_chars and _looks_usable_span(span_text):
                    spans.append(
                        EvidenceSpan(
                            doc_id=path.as_posix(),
                            page_number=page_index,
                            span_text=span_text,
                            start_char=start_char,
                            end_char=start_char + len(span_text),
                        )
                    )
                buffer = ""
            cursor += len(sentence) + 1

        if buffer and len(buffer) >= min_chars:
            span_text = buffer[:max_chars].strip()
            if _looks_usable_span(span_text):
                spans.append(
                    EvidenceSpan(
                        doc_id=path.as_posix(),
                        page_number=page_index,
                        span_text=span_text,
                        start_char=start_char,
                        end_char=start_char + len(span_text),
                    )
                )
    return spans


def _span_to_dict(span: EvidenceSpan) -> dict[str, Any]:
    return {
        "doc_id": span.doc_id,
        "page_number": span.page_number,
        "span_text": span.span_text,
        "start_char": span.start_char,
        "end_char": span.end_char,
    }


def _make_row(index: int, question_type: str, spans: list[EvidenceSpan]) -> dict[str, Any]:
    first = spans[0]
    stem = Path(first.doc_id).stem
    if question_type == "direct_fact":
        question = f"TODO: Write a direct fact question answerable from {stem}, page {first.page_number}."
        needs_parent_context = False
        needs_rewrite = False
        is_unanswerable = False
    elif question_type == "cross_chunk":
        question = f"TODO: Write a cross-chunk question requiring both provided evidence spans from {stem}."
        needs_parent_context = True
        needs_rewrite = False
        is_unanswerable = False
    elif question_type == "rewrite_needed":
        question = f"TODO: Write a question that needs query rewrite before retrieving this evidence from {stem}."
        needs_parent_context = False
        needs_rewrite = True
        is_unanswerable = False
    elif question_type == "ambiguous":
        question = f"TODO: Write an ambiguous question whose answer depends on clarifying this evidence from {stem}."
        needs_parent_context = True
        needs_rewrite = True
        is_unanswerable = False
    elif question_type == "no_answer":
        question = f"TODO: Write an unanswerable question that should be refused when only {stem} is available."
        needs_parent_context = False
        needs_rewrite = False
        is_unanswerable = True
    else:
        raise ValueError(f"unknown question_type: {question_type}")

    return {
        "id": f"custom-draft-{index:04d}",
        "question": question,
        "gold_answer": "" if is_unanswerable else "TODO: manually write the verified answer from the evidence spans.",
        "gold_doc_ids": sorted({span.doc_id for span in spans}),
        "gold_spans": [] if is_unanswerable else [_span_to_dict(span) for span in spans],
        "question_type": question_type,
        "needs_parent_context": needs_parent_context,
        "needs_rewrite": needs_rewrite,
        "is_unanswerable": is_unanswerable,
        "source_notes": "annotation draft generated from extracted PDF text; must be manually reviewed before official use",
        "annotation_status": "draft_needs_review",
        "evidence_preview": [_span_to_dict(span) for span in spans],
    }


def build_draft(
    source_dir: Path,
    seed: int,
    min_chars: int,
    max_chars: int,
    max_samples: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = random.Random(seed)
    pdfs = sorted(source_dir.glob("*.pdf"))
    spans: list[EvidenceSpan] = []
    span_counts: dict[str, int] = {}
    for pdf in pdfs:
        extracted = _extract_pdf_spans(pdf, min_chars=min_chars, max_chars=max_chars)
        span_counts[pdf.as_posix()] = len(extracted)
        spans.extend(extracted)

    if not spans:
        return [], {
            "status": "empty",
            "reason": "no extractable PDF spans found",
            "source_dir": str(source_dir),
            "created_at": _utc_now(),
            "seed": seed,
            "span_counts": span_counts,
        }

    rng.shuffle(spans)
    rows: list[dict[str, Any]] = []
    index = 1
    for question_type, target_count in QUESTION_TYPE_TARGETS.items():
        for _ in range(target_count):
            if len(rows) >= max_samples:
                break
            if question_type == "cross_chunk" and len(spans) >= 2:
                first = spans[(index * 2) % len(spans)]
                second = spans[(index * 2 + 1) % len(spans)]
                selected = [first, second]
            else:
                selected = [spans[index % len(spans)]]
            rows.append(_make_row(index=index, question_type=question_type, spans=selected))
            index += 1
        if len(rows) >= max_samples:
            break

    manifest = {
        "status": "draft_needs_manual_review",
        "source_dir": str(source_dir),
        "created_at": _utc_now(),
        "seed": seed,
        "sample_count": len(rows),
        "span_counts": span_counts,
        "question_type_targets": QUESTION_TYPE_TARGETS,
        "notes": [
            "This file is an annotation aid, not an official benchmark.",
            "Rows intentionally keep TODO questions and answers so they cannot pass official validation by accident.",
            "After manual review, copy reviewed rows into custom_eval.jsonl and run validate_custom_eval.py --fail-on-invalid.",
        ],
    }
    return rows, manifest


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a draft annotation pack for custom RAG eval.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-file", type=Path, default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--manifest-file", type=Path, default=DEFAULT_MANIFEST_FILE)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-chars", type=int, default=180)
    parser.add_argument("--max-chars", type=int, default=700)
    parser.add_argument("--max-samples", type=int, default=50)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows, manifest = build_draft(
        source_dir=args.source_dir,
        seed=args.seed,
        min_chars=args.min_chars,
        max_chars=args.max_chars,
        max_samples=args.max_samples,
    )
    _write_jsonl(args.output_file, rows)
    _write_json(args.manifest_file, manifest)
    print(f"wrote {len(rows)} annotation draft rows to {args.output_file}")
    print(f"wrote manifest to {args.manifest_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
