from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sys
import time
from typing import Any
from uuid import uuid4

from config import load_config_file

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from latency_contract import (  # noqa: E402
    LatencyEvent,
    LatencyEvalConfig,
    LatencySampleResult,
    compute_latency_summary,
    load_jsonl,
    normalize_tags,
    write_json,
    write_jsonl,
    write_markdown_summary,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _stable_hash(payload: Any) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


@dataclass(slots=True)
class BackendHooks:
    chat_with_agent: Any
    chat_with_agent_stream: Any


def _load_backend_hooks() -> BackendHooks:
    try:
        from agent import chat_with_agent, chat_with_agent_stream
    except Exception as exc:  # pragma: no cover - import error path is environment dependent
        raise RuntimeError(
            "Failed to import backend agent helpers. Make sure backend dependencies and env vars are available."
        ) from exc
    return BackendHooks(chat_with_agent=chat_with_agent, chat_with_agent_stream=chat_with_agent_stream)


def _load_samples(config: LatencyEvalConfig) -> list[dict[str, Any]]:
    path = Path(config.dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    rows = load_jsonl(path, limit=config.sample_limit)
    rng = random.Random(config.seed)
    rng.shuffle(rows)
    if config.sample_limit is not None:
        rows = rows[: config.sample_limit]
    return rows


def _coerce_sample(row: dict[str, Any], idx: int, config: LatencyEvalConfig) -> dict[str, Any]:
    question = str(row.get(config.question_key, "")).strip()
    if not question:
        raise ValueError(f"Sample #{idx} missing question field: {config.question_key}")
    sample_id = str(row.get(config.sample_id_key) or f"sample_{idx:04d}")
    expected_answer = row.get(config.answer_key)
    tags = normalize_tags(row.get(config.tags_key))
    return {
        "sample_id": sample_id,
        "question": question,
        "expected_answer": str(expected_answer).strip() if expected_answer else None,
        "tags": tags,
        "raw": row,
    }


async def _run_stream_sample(
    hooks: BackendHooks,
    sample: dict[str, Any],
    config: LatencyEvalConfig,
    run_id: str,
) -> tuple[LatencySampleResult, list[LatencyEvent]]:
    started_iso = _utc_now_iso()
    started_ms = _now_ms()
    events: list[LatencyEvent] = []
    response_text = ""
    rag_trace: dict[str, Any] | None = None
    first_event_ms: float | None = None
    first_token_ms: float | None = None
    trace_event_ms: float | None = None
    status = "ok"
    error: str | None = None
    request_id = uuid4().hex
    session_id = f"{config.session_prefix}_{run_id}_{sample['sample_id']}"

    try:
        async for chunk in hooks.chat_with_agent_stream(
            user_text=sample["question"],
            user_id=config.user_id,
            session_id=session_id,
        ):
            elapsed = _now_ms() - started_ms
            if first_event_ms is None:
                first_event_ms = elapsed
            if not isinstance(chunk, str) or not chunk.startswith("data: "):
                continue
            payload_text = chunk[len("data: ") :].strip()
            if payload_text == "[DONE]":
                continue
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                payload = {"raw": payload_text}
            event_type = str(payload.get("type", "unknown"))
            event_payload = {k: v for k, v in payload.items() if k != "type"}
            events.append(
                LatencyEvent(
                    run_id=run_id,
                    sample_id=sample["sample_id"],
                    variant="stream",
                    request_id=request_id,
                    event_index=len(events),
                    event_type=event_type,
                    at_ms=elapsed,
                    payload=event_payload,
                )
            )
            if event_type == "content":
                response_text += str(payload.get("content", ""))
                if first_token_ms is None:
                    first_token_ms = elapsed
            elif event_type == "trace":
                rag_trace = payload.get("rag_trace") or rag_trace
                if trace_event_ms is None:
                    trace_event_ms = elapsed
            elif event_type == "error":
                status = "error"
                error = str(payload.get("content") or payload.get("error") or "stream_error")
                break
    except Exception as exc:
        status = "error"
        error = str(exc)

    finished_iso = _utc_now_iso()
    duration_ms = _now_ms() - started_ms
    result = LatencySampleResult(
        run_id=run_id,
        sample_id=sample["sample_id"],
        variant="stream",
        request_id=request_id,
        question=sample["question"],
        status=status,
        started_at=started_iso,
        finished_at=finished_iso,
        duration_ms=duration_ms,
        time_to_first_event_ms=first_event_ms,
        time_to_first_token_ms=first_token_ms,
        time_to_trace_event_ms=trace_event_ms,
        response_text=response_text,
        rag_trace=rag_trace,
        error=error,
        config_hash=_stable_hash(config.to_dict()),
        expected_answer=sample.get("expected_answer"),
        tags=sample.get("tags", []),
        event_count=len(events),
    )
    return result, events


def _run_sync_sample(
    hooks: BackendHooks,
    sample: dict[str, Any],
    config: LatencyEvalConfig,
    run_id: str,
) -> tuple[LatencySampleResult, list[LatencyEvent]]:
    started_iso = _utc_now_iso()
    started_ms = _now_ms()
    status = "ok"
    error: str | None = None
    response_text = ""
    rag_trace: dict[str, Any] | None = None
    request_id = uuid4().hex
    session_id = f"{config.session_prefix}_{run_id}_{sample['sample_id']}"
    events: list[LatencyEvent] = []
    try:
        result = hooks.chat_with_agent(
            user_text=sample["question"],
            user_id=config.user_id,
            session_id=session_id,
        )
        if isinstance(result, dict):
            response_text = str(result.get("response", "") or "")
            rag_trace = result.get("rag_trace") or None
        else:
            response_text = str(result or "")
    except Exception as exc:
        status = "error"
        error = str(exc)

    finished_iso = _utc_now_iso()
    duration_ms = _now_ms() - started_ms
    result = LatencySampleResult(
        run_id=run_id,
        sample_id=sample["sample_id"],
        variant="sync",
        request_id=request_id,
        question=sample["question"],
        status=status,
        started_at=started_iso,
        finished_at=finished_iso,
        duration_ms=duration_ms,
        response_text=response_text,
        rag_trace=rag_trace,
        error=error,
        config_hash=_stable_hash(config.to_dict()),
        expected_answer=sample.get("expected_answer"),
        tags=sample.get("tags", []),
        event_count=len(events),
    )
    return result, events


def _build_run_id(config: LatencyEvalConfig) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = _stable_hash({"dataset_path": config.dataset_path, "mode": config.mode, "seed": config.seed})
    return f"latency_{stamp}_{suffix}"


def _dataset_label(dataset_path: str) -> str:
    path = Path(dataset_path)
    parent = path.parent.name.strip()
    stem = path.stem.strip()
    if parent and stem:
        return f"{parent}/{stem}"
    if stem:
        return stem
    return str(path)


def run_latency_eval(config: LatencyEvalConfig) -> dict[str, Any]:
    hooks = _load_backend_hooks()
    samples = [_coerce_sample(row, idx, config) for idx, row in enumerate(_load_samples(config), 1)]
    run_id = _build_run_id(config)
    output_dir = Path(config.output_dir) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    all_results: list[LatencySampleResult] = []
    all_events: list[LatencyEvent] = []
    summary_by_variant: dict[str, dict[str, Any]] = {}

    variants: list[str]
    if config.mode == "both":
        variants = ["sync", "stream"]
    elif config.mode in {"sync", "stream"}:
        variants = [config.mode]
    else:
        raise ValueError("mode must be one of: sync, stream, both")

    for variant in variants:
        for repeat_index in range(max(1, config.repeat)):
            for sample in samples:
                if variant == "stream":
                    result, events = asyncio.run(_run_stream_sample(hooks, sample, config, run_id))
                else:
                    result, events = _run_sync_sample(hooks, sample, config, run_id)
                result.variant = f"{variant}#{repeat_index + 1}" if config.repeat > 1 else variant
                if events:
                    for event in events:
                        event.variant = result.variant
                        all_events.append(event)
                all_results.append(result)

    summary = compute_latency_summary(run_id, config.dataset_path, config.mode, all_results)
    for variant in sorted({item.variant for item in all_results}):
        variant_results = [item for item in all_results if item.variant == variant]
        summary_by_variant[variant] = compute_latency_summary(run_id, config.dataset_path, variant, variant_results).to_dict()
    manifest = {
        "run_id": run_id,
        "created_at": _utc_now_iso(),
        "config": config.to_dict(),
        "files": {
            "config": "config.json",
            "results": "samples.jsonl",
            "events": "events.jsonl",
            "summary": "summary.json",
            "summary_by_variant": "summary_by_variant.json",
            "summary_md": "summary.md",
        },
    }

    write_json(output_dir / "config.json", config.to_dict())
    write_json(output_dir / "manifest.json", manifest)
    write_jsonl(output_dir / "samples.jsonl", all_results)
    write_jsonl(output_dir / "events.jsonl", all_events)
    write_json(output_dir / "summary.json", summary.to_dict())
    write_json(output_dir / "summary_by_variant.json", summary_by_variant)
    write_markdown_summary(output_dir / "summary.md", summary)
    write_json(
        output_dir / "metadata.json",
        {
            "config": {
                "name": "latency_eval",
                "kind": "latency",
                "dataset": _dataset_label(config.dataset_path),
                "variant": config.mode,
                "config_hash": _stable_hash(config.to_dict()),
                "seed": config.seed,
                "output_dir": str(output_dir.parent),
                "params": config.to_dict(),
                "tags": ["official", "baseline"],
            },
            "summary": summary.to_dict(),
        },
    )

    return {
        "run_id": run_id,
        "output_dir": str(output_dir),
        "summary": summary.to_dict(),
        "summary_by_variant": summary_by_variant,
        "result_count": len(all_results),
        "event_count": len(all_events),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Latency / trace eval skeleton for SuperMew.")
    parser.add_argument("--config", default=None, help="Optional JSON/YAML config file.")
    parser.add_argument("--dataset-path", required=False, help="Path to a jsonl dataset with question rows.")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "eval" / "outputs"), help="Directory for run outputs.")
    parser.add_argument("--mode", choices=["sync", "stream", "both"], default="both")
    parser.add_argument("--sample-limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--user-id", default="latency_eval_user")
    parser.add_argument("--session-prefix", default="latency_eval")
    parser.add_argument("--request-timeout-s", type=float, default=None)
    parser.add_argument("--question-key", default="question")
    parser.add_argument("--sample-id-key", default="sample_id")
    parser.add_argument("--answer-key", default="expected_answer")
    parser.add_argument("--tags-key", default="tags")
    return parser


def _resolve_latency_config(args: argparse.Namespace) -> LatencyEvalConfig:
    config_data: dict[str, Any] = {}
    if args.config:
        loaded = load_config_file(args.config)
        if isinstance(loaded, dict):
            config_data = dict(loaded)

    params = dict(config_data.get("params") or {})

    def pick(name: str, default: Any = None) -> Any:
        value = getattr(args, name)
        if value is not None:
            return value
        if name in config_data:
            return config_data[name]
        return params.get(name, default)

    dataset_path = pick("dataset_path")
    if not dataset_path:
        raise ValueError("dataset_path is required via --dataset-path or --config")

    return LatencyEvalConfig(
        dataset_path=dataset_path,
        output_dir=pick("output_dir", str(REPO_ROOT / "eval" / "outputs")),
        mode=pick("mode", "both"),
        sample_limit=pick("sample_limit"),
        seed=int(pick("seed", 42)),
        user_id=pick("user_id", "latency_eval_user"),
        session_prefix=pick("session_prefix", "latency_eval"),
        repeat=int(pick("repeat", params.get("repeats", 1) or 1)),
        request_timeout_s=pick("request_timeout_s"),
        question_key=pick("question_key", "question"),
        sample_id_key=pick("sample_id_key", "sample_id"),
        answer_key=pick("answer_key", "expected_answer"),
        tags_key=pick("tags_key", "tags"),
    )


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    config = _resolve_latency_config(args)
    result = run_latency_eval(config)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
