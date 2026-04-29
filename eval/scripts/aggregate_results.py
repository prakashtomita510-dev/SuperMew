from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from datetime import datetime
from typing import Any

from results import write_csv


REPORTS_DIR = Path("eval/outputs/reports")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_metadata_files(outputs_root: Path) -> list[Path]:
    return sorted(outputs_root.glob("**/metadata.json"))


def _parse_generated_at(payload: dict[str, Any], metadata_path: Path) -> datetime:
    generated_at = payload.get("summary", {}).get("generated_at")
    if isinstance(generated_at, str):
        try:
            return datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.fromtimestamp(metadata_path.stat().st_mtime)


def _is_smoke_payload(payload: dict[str, Any]) -> bool:
    config = payload.get("config", {})
    kind = str(config.get("kind") or "")
    tags = set(config.get("tags") or [])
    return kind.endswith("_smoke") or "smoke" in tags or "not_official" in tags


def aggregate(outputs_root: Path, include_smoke: bool = False) -> tuple[list[dict[str, Any]], str]:
    latest_payloads: dict[tuple[str | None, str | None, str | None], tuple[datetime, Path, dict[str, Any]]] = {}
    lines = ["# Results Summary", ""]
    for metadata_path in _find_metadata_files(outputs_root):
        payload = _read_json(metadata_path)
        if not include_smoke and _is_smoke_payload(payload):
            continue
        config = payload.get("config", {})
        key = (
            config.get("kind"),
            config.get("dataset"),
            config.get("variant"),
        )
        current = (_parse_generated_at(payload, metadata_path), metadata_path, payload)
        previous = latest_payloads.get(key)
        if previous is None or current[0] >= previous[0]:
            latest_payloads[key] = current

    rows = []
    for _, metadata_path, payload in sorted(
        latest_payloads.values(),
        key=lambda item: (
            item[2].get("config", {}).get("kind") or "",
            item[2].get("config", {}).get("dataset") or "",
            item[2].get("config", {}).get("variant") or "",
        ),
    ):
        config = payload.get("config", {})
        summary = payload.get("summary", {})
        row = {
            "kind": config.get("kind"),
            "dataset": config.get("dataset"),
            "variant": config.get("variant"),
            "config_hash": config.get("config_hash"),
        }
        row.update(summary)
        rows.append(row)
        lines.append(
            f"- `{config.get('kind')}` / `{config.get('variant')}` on `{config.get('dataset')}`: "
            f"{json.dumps(summary, ensure_ascii=False, sort_keys=True)} "
            f"(source: `{metadata_path.as_posix()}`)"
        )
    if len(lines) == 2:
        lines.append("- No metadata.json files were found under the output root yet.")
    return rows, "\n".join(lines) + "\n"


def _write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate eval outputs into report-ready tables.")
    parser.add_argument("--outputs-root", type=Path, default=Path("eval/outputs"))
    parser.add_argument("--reports-dir", type=Path, default=REPORTS_DIR)
    parser.add_argument("--include-smoke", action="store_true", help="Include smoke / not_official runs in aggregate reports.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows, summary_md = aggregate(args.outputs_root, include_smoke=args.include_smoke)
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, args.reports_dir / "results_table.csv")
    write_csv([row for row in rows if row.get("kind") == "retrieval"], args.reports_dir / "retrieval_metrics.csv")
    write_csv([row for row in rows if row.get("kind") == "chunking"], args.reports_dir / "chunking_metrics.csv")
    write_csv([row for row in rows if row.get("kind") == "rewrite"], args.reports_dir / "rewrite_metrics.csv")
    write_csv([row for row in rows if row.get("kind") == "latency"], args.reports_dir / "latency_metrics.csv")
    write_csv([row for row in rows if row.get("kind") == "rag"], args.reports_dir / "rag_metrics.csv")
    _write_markdown(args.reports_dir / "results_summary.md", summary_md)
    print(f"wrote reports to {args.reports_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
