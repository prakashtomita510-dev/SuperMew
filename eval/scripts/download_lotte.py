"""Normalizer for the local LoTTE evaluation dataset."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DOMAINS = ("technology", "science", "writing")
DEFAULT_SPLITS = ("dev", "test")
DEFAULT_ROOT_DIR = Path("eval/datasets/lotte")
DEFAULT_SOURCE_DIR = DEFAULT_ROOT_DIR / "lotte"


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
    source_dir: Path,
    domains: list[str],
    splits: list[str],
    sample_limit: int | None,
) -> dict[str, Any]:
    plan: list[dict[str, Any]] = []
    for domain in domains:
        for split in splits:
            for query_set in ("forum", "search"):
                plan.append(
                    {
                        "domain": domain,
                        "split": split,
                        "query_set": query_set,
                        "relative_output": f"normalized/{domain}/{split}.{query_set}.jsonl",
                        "source_path": str(source_dir / domain / split / f"qas.{query_set}.jsonl"),
                    }
                )

    return {
        "dataset": "lotte",
        "created_at": _utc_now(),
        "output_dir": str(output_dir),
        "source_dir": str(source_dir),
        "status": "ready_for_processing",
        "domains": domains,
        "splits": splits,
        "sample_limit": sample_limit,
        "notes": [
            "Source: Local LoTTE extracted from tarball.",
            "Normalization covers both forum and search query rows.",
            "Corpus preparation should be handled through ingest_lotte.py.",
        ],
        "processing_plan": plan,
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _normalize_row(row: dict[str, Any], domain: str) -> dict[str, Any]:
    return {
        "query_id": str(row.get("qid") or ""),
        "query_text": str(row.get("query") or ""),
        "relevant_doc_ids": [str(item) for item in row.get("answer_pids", [])],
        "domain": domain,
    }


def process_local_if_requested(manifest: dict[str, Any], output_dir: Path, run: bool) -> list[str]:
    if not run:
        return ["processing disabled; emitted manifest only"]

    messages: list[str] = []
    sample_limit = manifest.get("sample_limit")

    for item in manifest["processing_plan"]:
        source_path = Path(item["source_path"])
        target = output_dir / item["relative_output"]
        domain = item["domain"]
        query_set = item["query_set"]

        if not source_path.exists():
            messages.append(f"SKIP {domain}:{item['split']}:{query_set} - source not found at {source_path}")
            continue

        rows = []
        with source_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if sample_limit is not None and len(rows) >= sample_limit:
                    break
                raw_row = json.loads(line)
                rows.append(_normalize_row(raw_row, domain))

        _write_jsonl(target, rows)
        messages.append(f"processed {domain}:{item['split']}:{query_set} -> {len(rows)} rows at {target}")

        if query_set == "forum":
            legacy_target = output_dir / f"normalized/{domain}/{item['split']}.jsonl"
            _write_jsonl(legacy_target, rows)
            messages.append(f"updated legacy alias {domain}:{item['split']} -> {legacy_target}")

    return messages


def _write_status(output_dir: Path, payload: dict[str, Any]) -> None:
    _write_json(output_dir / "processing_status.json", payload)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ROOT_DIR, help="Where to place the normalized dataset.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR, help="Path to local LoTTE root (containing domain folders).")
    parser.add_argument("--domains", type=str, default=",".join(DEFAULT_DOMAINS), help="Comma-separated LoTTE domains.")
    parser.add_argument("--splits", type=str, default=",".join(DEFAULT_SPLITS), help="Comma-separated LoTTE splits.")
    parser.add_argument("--sample-limit", type=int, default=None, help="Optional cap on the number of normalized rows to retain.")
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run normalization on local files.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir: Path = args.output_dir
    source_dir: Path = args.source_dir
    domains = _parse_csv(args.domains, DEFAULT_DOMAINS)
    splits = _parse_csv(args.splits, DEFAULT_SPLITS)

    manifest = build_manifest(output_dir, source_dir, domains, splits, args.sample_limit)
    _write_json(output_dir / "manifest.json", manifest)
    _write_text(
        output_dir / "README.md",
        "# LoTTE normalized dataset\n\n"
        "This directory contains normalized rows for LoTTE evaluation.\n\n"
        "Generated from local source by `eval/scripts/download_lotte.py`.\n",
    )

    try:
        messages = process_local_if_requested(manifest, output_dir, args.run)
        _write_status(
            output_dir,
            {
                "status": "ok",
                "run_requested": args.run,
                "messages": messages,
            },
        )
    except Exception as exc:
        messages = [f"processing failed: {exc!r}"]
        _write_status(
            output_dir,
            {
                "status": "error",
                "run_requested": args.run,
                "error": repr(exc),
                "messages": messages,
            },
        )
    for message in messages:
        print(message)

    print(f"wrote manifest to {output_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
