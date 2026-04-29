from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
load_dotenv(REPO_ROOT / ".env")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe Google embedding rate limits with small controlled requests.")
    parser.add_argument("--model", default=os.getenv("EMBEDDER", "gemini-embedding-001"))
    parser.add_argument("--batch-sizes", nargs="+", type=int, default=[1, 2, 4, 8])
    parser.add_argument("--intervals", nargs="+", type=float, default=[1.0, 3.0, 6.0, 10.0])
    parser.add_argument("--attempts-per-config", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--stop-after-first-429", action="store_true")
    parser.add_argument(
        "--output-path",
        type=Path,
        default=REPO_ROOT / "eval" / "outputs" / "reports" / "google_embed_probe.jsonl",
    )
    return parser.parse_args()


def load_env() -> tuple[str, str, str]:
    base_url = os.getenv("EMBEDDING_BASE_URL", "").rstrip("/")
    api_key = os.getenv("EMBEDDING_API_KEY", "")
    model = os.getenv("EMBEDDER", "")
    if not base_url or not api_key:
        raise RuntimeError("EMBEDDING_BASE_URL / EMBEDDING_API_KEY missing")
    if base_url.endswith("/openai"):
        base_url = base_url[:-7]
    return base_url, api_key, model


def make_texts(batch_size: int, ordinal: int) -> list[str]:
    return [
        f"probe request {ordinal} item {idx} about google docs styles and markdown"
        for idx in range(batch_size)
    ]


def build_payload(model_name: str, texts: list[str]) -> dict:
    model_path = model_name if model_name.startswith("models/") else f"models/{model_name}"
    return {
        "requests": [
            {
                "model": model_path,
                "content": {"parts": [{"text": text}]},
            }
            for text in texts
        ]
    }


def main() -> int:
    args = parse_args()
    base_url, api_key, env_model = load_env()
    model_name = args.model or env_model or "gemini-embedding-001"
    endpoint = f"{base_url}/{model_name if model_name.startswith('models/') else f'models/{model_name}'}:batchEmbedContents"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    if args.output_path.exists():
        args.output_path.unlink()

    summary_rows: list[dict] = []
    request_index = 0

    with args.output_path.open("a", encoding="utf-8") as out:
        for batch_size in args.batch_sizes:
            for interval_seconds in args.intervals:
                config_rows = []
                for attempt in range(1, args.attempts_per_config + 1):
                    request_index += 1
                    texts = make_texts(batch_size, request_index)
                    payload = build_payload(model_name, texts)
                    started = time.perf_counter()
                    error_text = None
                    retry_after = None
                    vector_dim = None
                    embedding_count = 0
                    status_code = None

                    try:
                        response = requests.post(
                            endpoint,
                            headers=headers,
                            json=payload,
                            timeout=args.timeout_seconds,
                        )
                        status_code = response.status_code
                        retry_after = response.headers.get("Retry-After")
                        body = response.json()
                        if response.ok:
                            embeddings = body.get("embeddings", [])
                            embedding_count = len(embeddings)
                            if embeddings:
                                vector_dim = len(embeddings[0].get("values", []))
                        else:
                            error_text = body.get("error", {}).get("message") or response.text
                    except Exception as exc:  # noqa: BLE001
                        error_text = str(exc)

                    latency_ms = round((time.perf_counter() - started) * 1000, 2)
                    row = {
                        "timestamp": utc_now(),
                        "model": model_name,
                        "batch_size": batch_size,
                        "interval_seconds": interval_seconds,
                        "attempt": attempt,
                        "status_code": status_code,
                        "ok": status_code == 200,
                        "embedding_count": embedding_count,
                        "vector_dim": vector_dim,
                        "latency_ms": latency_ms,
                        "retry_after": retry_after,
                        "error": error_text,
                    }
                    config_rows.append(row)
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    out.flush()
                    print(json.dumps(row, ensure_ascii=False), flush=True)

                    if status_code == 429 and args.stop_after_first_429:
                        break
                    if attempt < args.attempts_per_config:
                        time.sleep(interval_seconds)

                ok_count = sum(1 for row in config_rows if row["ok"])
                summary = {
                    "model": model_name,
                    "batch_size": batch_size,
                    "interval_seconds": interval_seconds,
                    "attempts": len(config_rows),
                    "ok_count": ok_count,
                    "rate_limited_count": sum(1 for row in config_rows if row["status_code"] == 429),
                    "other_error_count": sum(
                        1
                        for row in config_rows
                        if (row["status_code"] not in (200, 429) and row["status_code"] is not None) or (
                            row["status_code"] is None and row["error"]
                        )
                    ),
                    "avg_latency_ms": round(
                        sum(row["latency_ms"] for row in config_rows) / len(config_rows), 2
                    )
                    if config_rows
                    else None,
                }
                summary_rows.append(summary)

    print("=== probe summary ===")
    for row in summary_rows:
        print(json.dumps(row, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
