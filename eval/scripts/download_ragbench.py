"""Downloader / normalizer for the RAGBench evaluation dataset."""

from __future__ import annotations

import argparse
import json
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_SPLITS = ("test",)
DEFAULT_OUTPUT_DIR = Path("eval/datasets/ragbench")
DEFAULT_DATASET_ID = "galileo-ai/ragbench"
DEFAULT_SUBSETS = ("techqa", "hotpotqa", "emanual")
VIEWER_ROWS_URL = "https://datasets-server.huggingface.co/rows"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_csv(values: str | None, fallback: Iterable[str]) -> list[str]:
    if not values:
        return list(fallback)
    items = [item.strip() for item in values.split(",")]
    return [item for item in items if item]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_manifest(
    output_dir: Path,
    dataset_id: str,
    subsets: list[str],
    splits: list[str],
    sample_limit: int | None,
) -> dict[str, Any]:
    plan: list[dict[str, Any]] = []
    for subset in subsets:
        for split in splits:
            plan.append(
                {
                    "subset": subset,
                    "split": split,
                    "relative_output": f"normalized/{subset}/{split}.jsonl",
                }
            )

    return {
        "dataset": "ragbench",
        "created_at": _utc_now(),
        "output_dir": str(output_dir),
        "status": "ready_for_download",
        "dataset_id": dataset_id,
        "subsets": subsets,
        "splits": splits,
        "sample_limit": sample_limit,
        "notes": [
            "Default source confirmed via Hugging Face: galileo-ai/ragbench.",
            "Normalization keeps question, documents, response, subset name, and available explainability labels.",
        ],
        "download_plan": plan,
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _normalize_row(row: dict[str, Any], subset: str) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "question": str(row.get("question") or ""),
        "context_docs": row.get("documents") or [],
        "gold_answer": str(row.get("response") or ""),
        "task_type": str(row.get("dataset_name") or subset),
        "labels": {
            "adherence_score": row.get("adherence_score"),
            "relevance_score": row.get("relevance_score"),
            "utilization_score": row.get("utilization_score"),
            "completeness_score": row.get("completeness_score"),
            "overall_supported_explanation": row.get("overall_supported_explanation"),
            "relevance_explanation": row.get("relevance_explanation"),
        },
    }


def download_if_requested(manifest: dict[str, Any], output_dir: Path, download: bool) -> list[str]:
    if not download:
        return ["download disabled; emitted manifest only"]

    messages: list[str] = []
    dataset_id = str(manifest["dataset_id"])
    for item in manifest["download_plan"]:
        target = output_dir / item["relative_output"]
        target.parent.mkdir(parents=True, exist_ok=True)
        sample_limit = manifest.get("sample_limit")
        normalized_rows = _fetch_rows(
            dataset_id=dataset_id,
            subset=item["subset"],
            split=item["split"],
            sample_limit=sample_limit if isinstance(sample_limit, int) else None,
        )
        _write_jsonl(target, normalized_rows)
        messages.append(f"loaded {dataset_id}:{item['subset']}:{item['split']} -> {len(normalized_rows)} rows")

    return messages


def _fetch_rows(dataset_id: str, subset: str, split: str, sample_limit: int | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = 100
    while True:
        length = page_size if sample_limit is None else min(page_size, sample_limit - len(rows))
        if length <= 0:
            break
        response = requests.get(
            VIEWER_ROWS_URL,
            params={
                "dataset": dataset_id,
                "config": subset,
                "split": split,
                "offset": offset,
                "length": length,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        batch = [_normalize_row(item.get("row", {}), subset) for item in payload.get("rows", [])]
        rows.extend(batch)
        if len(batch) < length:
            break
        offset += len(batch)
    return rows


def _write_download_status(output_dir: Path, payload: dict[str, Any]) -> None:
    _write_json(output_dir / "download_status.json", payload)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Where to place the generated dataset skeleton.")
    parser.add_argument("--dataset-id", type=str, default=DEFAULT_DATASET_ID, help="Hugging Face dataset id.")
    parser.add_argument("--subsets", type=str, default=",".join(DEFAULT_SUBSETS), help="Comma-separated RAGBench subset names.")
    parser.add_argument("--splits", type=str, default=",".join(DEFAULT_SPLITS), help="Comma-separated RAGBench splits.")
    parser.add_argument("--sample-limit", type=int, default=None, help="Optional cap used later by sampling logic.")
    parser.add_argument(
        "--download",
        action="store_true",
        help="Fetch normalized rows from the Hugging Face dataset viewer API.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir: Path = args.output_dir
    splits = _parse_csv(args.splits, DEFAULT_SPLITS)
    subsets = _parse_csv(args.subsets, DEFAULT_SUBSETS)

    manifest = build_manifest(output_dir, args.dataset_id, subsets, splits, args.sample_limit)
    _write_json(output_dir / "manifest.json", manifest)
    _write_text(
        output_dir / "README.md",
        "# RAGBench dataset skeleton\n\n"
        "This directory is generated by `eval/scripts/download_ragbench.py`.\n\n"
        "It currently contains a manifest and a Hugging Face download plan.\n"
        "Run with `--download` to materialize normalized rows through the Hugging Face dataset viewer API.\n",
    )

    try:
        messages = download_if_requested(manifest, output_dir, args.download)
        _write_download_status(
            output_dir,
            {
                "status": "ok",
                "download_requested": args.download,
                "messages": messages,
            },
        )
    except Exception as exc:
        messages = [f"download failed: {exc!r}"]
        _write_download_status(
            output_dir,
            {
                "status": "error",
                "download_requested": args.download,
                "error": repr(exc),
                "messages": messages,
            },
        )
    for message in messages:
        print(message)

    print(f"wrote manifest to {output_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
