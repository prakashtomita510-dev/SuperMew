from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return float(ordered[lower])
    weight = rank - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def _safe_mean(values: list[float]) -> float | None:
    return float(mean(values)) if values else None


@dataclass(slots=True)
class LatencyEvalConfig:
    dataset_path: str
    output_dir: str
    mode: str = "both"
    sample_limit: int | None = None
    seed: int = 42
    user_id: str = "latency_eval_user"
    session_prefix: str = "latency_eval"
    repeat: int = 1
    request_timeout_s: float | None = None
    question_key: str = "question"
    sample_id_key: str = "sample_id"
    answer_key: str = "expected_answer"
    tags_key: str = "tags"
    raw_keep_events: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LatencyEvent:
    run_id: str
    sample_id: str
    variant: str
    request_id: str
    event_index: int
    event_type: str
    at_ms: float
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LatencySampleResult:
    run_id: str
    sample_id: str
    variant: str
    request_id: str
    question: str
    status: str
    started_at: str
    finished_at: str
    duration_ms: float
    time_to_first_event_ms: float | None = None
    time_to_first_token_ms: float | None = None
    time_to_trace_event_ms: float | None = None
    response_text: str = ""
    rag_trace: dict[str, Any] | None = None
    error: str | None = None
    config_hash: str | None = None
    expected_answer: str | None = None
    tags: list[str] = field(default_factory=list)
    event_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LatencySummary:
    run_id: str
    dataset_path: str
    mode: str
    sample_count: int
    success_count: int
    error_count: int
    mean_duration_ms: float | None
    p50_duration_ms: float | None
    p95_duration_ms: float | None
    mean_time_to_first_event_ms: float | None
    p95_time_to_first_event_ms: float | None
    mean_time_to_first_token_ms: float | None
    p95_time_to_first_token_ms: float | None
    mean_time_to_trace_event_ms: float | None
    p95_time_to_trace_event_ms: float | None
    trace_coverage_rate: float | None
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(value)]


def load_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
            if limit is not None and len(rows) >= limit:
                break
    return rows


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any] | Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            if hasattr(row, "to_dict"):
                payload = row.to_dict()  # type: ignore[assignment]
            elif isinstance(row, Mapping):
                payload = dict(row)
            else:
                payload = row
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_markdown_summary(path: Path, summary: LatencySummary) -> None:
    data = summary.to_dict()
    lines = [
        "# Latency Summary",
        "",
        f"- run_id: `{data['run_id']}`",
        f"- dataset_path: `{data['dataset_path']}`",
        f"- mode: `{data['mode']}`",
        f"- sample_count: `{data['sample_count']}`",
        f"- success_count: `{data['success_count']}`",
        f"- error_count: `{data['error_count']}`",
        f"- mean_duration_ms: `{data['mean_duration_ms']}`",
        f"- p95_duration_ms: `{data['p95_duration_ms']}`",
        f"- mean_time_to_first_event_ms: `{data['mean_time_to_first_event_ms']}`",
        f"- p95_time_to_first_event_ms: `{data['p95_time_to_first_event_ms']}`",
        f"- mean_time_to_first_token_ms: `{data['mean_time_to_first_token_ms']}`",
        f"- p95_time_to_first_token_ms: `{data['p95_time_to_first_token_ms']}`",
        f"- mean_time_to_trace_event_ms: `{data['mean_time_to_trace_event_ms']}`",
        f"- p95_time_to_trace_event_ms: `{data['p95_time_to_trace_event_ms']}`",
        f"- trace_coverage_rate: `{data['trace_coverage_rate']}`",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compute_latency_summary(run_id: str, dataset_path: str, mode: str, results: list[LatencySampleResult]) -> LatencySummary:
    durations = [item.duration_ms for item in results if item.status == "ok"]
    first_events = [item.time_to_first_event_ms for item in results if item.time_to_first_event_ms is not None]
    ttft = [item.time_to_first_token_ms for item in results if item.time_to_first_token_ms is not None]
    trace_ms = [item.time_to_trace_event_ms for item in results if item.time_to_trace_event_ms is not None]
    trace_basis = [item for item in results if item.variant.startswith("stream")]
    trace_basis = trace_basis if trace_basis else results
    trace_available = [item for item in trace_basis if item.status == "ok" and item.rag_trace]
    trace_basis_success_count = sum(1 for item in trace_basis if item.status == "ok")
    sample_count = len(results)
    success_count = sum(1 for item in results if item.status == "ok")
    error_count = sample_count - success_count
    return LatencySummary(
        run_id=run_id,
        dataset_path=dataset_path,
        mode=mode,
        sample_count=sample_count,
        success_count=success_count,
        error_count=error_count,
        mean_duration_ms=_safe_mean(durations),
        p50_duration_ms=_percentile(durations, 0.5),
        p95_duration_ms=_percentile(durations, 0.95),
        mean_time_to_first_event_ms=_safe_mean(first_events),
        p95_time_to_first_event_ms=_percentile(first_events, 0.95),
        mean_time_to_first_token_ms=_safe_mean(ttft),
        p95_time_to_first_token_ms=_percentile(ttft, 0.95),
        mean_time_to_trace_event_ms=_safe_mean(trace_ms),
        p95_time_to_trace_event_ms=_percentile(trace_ms, 0.95),
        trace_coverage_rate=(len(trace_available) / trace_basis_success_count) if trace_basis_success_count else None,
        generated_at=utc_now_iso(),
    )
