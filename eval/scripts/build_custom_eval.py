"""Build a skeleton custom-eval dataset from local source documents.

The current implementation is intentionally conservative:
- It can run even when the real document loader is not ready.
- It creates a schema-first JSONL sample set and a matching template.
- It marks every real ingestion point with TODOs so we can wire in a richer
  annotation workflow later without changing the output contract.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_SOURCE_DIR = Path("data/documents")
DEFAULT_OUTPUT_DIR = Path("eval/datasets/custom")
DEFAULT_OUTPUT_FILE = DEFAULT_OUTPUT_DIR / "custom_eval.jsonl"
DEFAULT_TEMPLATE_FILE = DEFAULT_OUTPUT_DIR / "custom_eval_template.jsonl"
SUPPORTED_SUFFIXES = {".pdf", ".md", ".txt", ".json", ".jsonl"}


@dataclass(frozen=True)
class SampleRow:
    id: str
    question: str
    gold_answer: str
    gold_doc_ids: list[str]
    gold_spans: list[dict[str, Any]]
    question_type: str
    needs_parent_context: bool
    needs_rewrite: bool
    is_unanswerable: bool
    source_notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "gold_answer": self.gold_answer,
            "gold_doc_ids": self.gold_doc_ids,
            "gold_spans": self.gold_spans,
            "question_type": self.question_type,
            "needs_parent_context": self.needs_parent_context,
            "needs_rewrite": self.needs_rewrite,
            "is_unanswerable": self.is_unanswerable,
            "source_notes": self.source_notes,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _scan_source_documents(source_dir: Path) -> list[Path]:
    if not source_dir.exists():
        return []
    files = [path for path in source_dir.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES]
    return sorted(files)


def _make_sample_row(source_path: Path, index: int) -> SampleRow:
    rel_path = source_path.as_posix()
    stem = source_path.stem or f"document-{index}"
    return SampleRow(
        id=f"custom-{index:04d}",
        question=f"What is the key fact that should be answerable from {stem}?",
        gold_answer="TODO: replace with a human-checked answer extracted from the document.",
        gold_doc_ids=[rel_path],
        gold_spans=[],
        question_type="document_summary",
        needs_parent_context=False,
        needs_rewrite=False,
        is_unanswerable=False,
        source_notes=f"auto-generated placeholder from source file {rel_path}",
    )


def _build_placeholder_rows(count: int) -> list[SampleRow]:
    rows: list[SampleRow] = []
    for index in range(count):
        rows.append(
            SampleRow(
                id=f"placeholder-{index:04d}",
                question="TODO: provide a real evaluation question.",
                gold_answer="TODO: provide a real evaluation answer.",
                gold_doc_ids=[],
                gold_spans=[],
                question_type="placeholder",
                needs_parent_context=False,
                needs_rewrite=False,
                is_unanswerable=False,
                source_notes="placeholder row generated because no source documents were found",
            )
        )
    return rows


def _build_template_row() -> dict[str, Any]:
    return SampleRow(
        id="example-0001",
        question="TODO: write a question that is answerable from the source document.",
        gold_answer="TODO: write the manually verified answer.",
        gold_doc_ids=["TODO:doc-id"],
        gold_spans=[
            {
                "doc_id": "TODO:doc-id",
                "span_text": "TODO: exact supporting span",
                "start_char": 0,
                "end_char": 0,
            }
        ],
        question_type="cross_chunk",
        needs_parent_context=True,
        needs_rewrite=False,
        is_unanswerable=False,
        source_notes="template row only; replace with a verified sample",
    ).to_dict()


def build_custom_eval(source_dir: Path, seed: int, max_samples: int | None, placeholder_count: int) -> tuple[list[SampleRow], dict[str, Any]]:
    rng = random.Random(seed)
    source_files = _scan_source_documents(source_dir)

    if not source_files:
        rows = _build_placeholder_rows(placeholder_count)
        manifest = {
            "status": "placeholder",
            "reason": "no source documents were discovered",
            "source_dir": str(source_dir),
            "created_at": _utc_now(),
            "seed": seed,
            "sample_count": len(rows),
            "notes": [
                "TODO: connect a real document loader before turning this into a benchmark dataset.",
                "TODO: replace placeholder rows with verified questions, answers, and doc ids.",
            ],
        }
        return rows, manifest

    ordered_files = list(source_files)
    rng.shuffle(ordered_files)
    if max_samples is not None:
        ordered_files = ordered_files[:max_samples]

    rows = [_make_sample_row(path, index) for index, path in enumerate(ordered_files, start=1)]
    manifest = {
        "status": "generated_from_local_files",
        "source_dir": str(source_dir),
        "created_at": _utc_now(),
        "seed": seed,
        "sample_count": len(rows),
        "notes": [
            "TODO: replace filename-based questions with annotation-backed evaluation items.",
            "TODO: add cross-chunk / rewrite-needed / unanswerable labels after manual review.",
            "TODO: use a proper loader for PDFs if the eval data should be grounded in document text instead of file names.",
        ],
    }
    return rows, manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR, help="Directory containing local source documents.")
    parser.add_argument("--output-file", type=Path, default=DEFAULT_OUTPUT_FILE, help="JSONL file to write the generated custom eval rows to.")
    parser.add_argument("--template-file", type=Path, default=DEFAULT_TEMPLATE_FILE, help="JSONL template file to write alongside the generated dataset.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for deterministic sampling.")
    parser.add_argument("--max-samples", type=int, default=None, help="Optional cap on the number of generated samples.")
    parser.add_argument("--placeholder-count", type=int, default=8, help="Number of placeholder rows to emit when no source documents exist.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows, manifest = build_custom_eval(
        source_dir=args.source_dir,
        seed=args.seed,
        max_samples=args.max_samples,
        placeholder_count=args.placeholder_count,
    )

    _write_jsonl(args.output_file, (row.to_dict() for row in rows))
    _write_jsonl(args.template_file, [_build_template_row()])
    _write_json(args.output_file.with_suffix(".manifest.json"), manifest)
    _write_json(
        args.template_file.with_suffix(".manifest.json"),
        {
            "created_at": _utc_now(),
            "template_file": str(args.template_file),
            "notes": ["TODO: keep this schema synchronized with the eval runner and annotator workflow."],
        },
    )

    print(f"wrote custom eval rows to {args.output_file}")
    print(f"wrote template rows to {args.template_file}")
    print(f"wrote manifest to {args.output_file.with_suffix('.manifest.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
