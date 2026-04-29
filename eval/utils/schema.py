from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EvalSample:
    sample_id: str
    question: str
    gold_answer: str | None = None
    gold_doc_ids: list[str] = field(default_factory=list)
    gold_spans: list[dict[str, Any]] = field(default_factory=list)
    question_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvalMetricRow:
    sample_id: str
    variant: str
    metrics: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, Any] = field(default_factory=dict)
    latency_ms: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvalRunResult:
    run_id: str
    dataset: str
    variant: str
    config_hash: str
    summary: dict[str, Any] = field(default_factory=dict)
    rows: list[EvalMetricRow] = field(default_factory=list)

