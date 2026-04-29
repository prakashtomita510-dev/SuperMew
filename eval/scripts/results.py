from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def ensure_parent_dir(path: str | Path) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _scalar_or_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default)


def flatten_record(record: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in record.items():
        compound_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            flat.update(flatten_record(value, compound_key))
        else:
            flat[compound_key] = _scalar_or_json(value)
    return flat


def write_jsonl(records: Iterable[Mapping[str, Any]], path: str | Path) -> Path:
    resolved = ensure_parent_dir(path)
    with resolved.open("w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=_json_default))
            fh.write("\n")
    return resolved


def write_csv(
    records: Iterable[Mapping[str, Any]],
    path: str | Path,
    fieldnames: Sequence[str] | None = None,
) -> Path:
    resolved = ensure_parent_dir(path)
    rows = [flatten_record(record) for record in records]
    columns = list(fieldnames) if fieldnames is not None else sorted({key for row in rows for key in row})
    if not columns and not rows:
        resolved.write_text("", encoding="utf-8")
        return resolved
    with resolved.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
    return resolved


def write_markdown_table(
    records: Iterable[Mapping[str, Any]],
    path: str | Path,
    columns: Sequence[str] | None = None,
) -> Path:
    resolved = ensure_parent_dir(path)
    rows = [flatten_record(record) for record in records]
    headers = list(columns) if columns is not None else sorted({key for row in rows for key in row})
    if not headers and not rows:
        resolved.write_text("", encoding="utf-8")
        return resolved

    def cell(value: Any) -> str:
        text = "" if value is None else str(value)
        return text.replace("|", "\\|")

    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(cell(row.get(header, "")) for header in headers) + " |")

    resolved.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return resolved


@dataclass(slots=True)
class ResultBundleWriter:
    output_dir: Path

    def write(
        self,
        *,
        prefix: str,
        records: Iterable[Mapping[str, Any]],
        metadata: Mapping[str, Any] | None = None,
        summary: str = "",
        csv_fieldnames: Sequence[str] | None = None,
        table_columns: Sequence[str] | None = None,
    ) -> dict[str, Path]:
        bundle_dir = self.output_dir / prefix
        bundle_dir.mkdir(parents=True, exist_ok=True)

        records_list = list(records)
        outputs = {
            "jsonl": write_jsonl(records_list, bundle_dir / "records.jsonl"),
            "csv": write_csv(records_list, bundle_dir / "records.csv", fieldnames=csv_fieldnames),
        }

        if metadata is not None:
            metadata_path = ensure_parent_dir(bundle_dir / "metadata.json")
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2, default=_json_default) + "\n",
                encoding="utf-8",
            )
            outputs["metadata"] = metadata_path

        if summary:
            summary_path = bundle_dir / "summary.md"
            summary_path.write_text(summary.rstrip() + "\n", encoding="utf-8")
            outputs["summary"] = summary_path

        if table_columns is not None:
            outputs["table"] = write_markdown_table(
                records_list,
                bundle_dir / "records.md",
                columns=table_columns,
            )

        return outputs
