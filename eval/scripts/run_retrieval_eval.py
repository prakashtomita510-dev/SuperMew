from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
from typing import Any

from config import EvalConfig, config_hash, load_config_file
from metrics import mrr_at_k, ndcg_at_k, recall_at_k, safe_mean
from results import ResultBundleWriter


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _doc_id(doc: dict[str, Any]) -> str:
    # Try to extract PID from chunk_id if it follows the lotte_{pid}::... pattern
    chunk_id = str(doc.get("chunk_id") or "")
    if chunk_id.startswith("lotte_"):
        # Pattern: lotte_12345::p0::l3::0 -> 12345
        try:
            return chunk_id.split("::")[0].replace("lotte_", "")
        except Exception:
            pass
    
    # Fallback to standard chunk_id or filename
    id_val = chunk_id or str(doc.get("filename") or "")
    # Also handle raw pid in metadata if available (added during ingestion)
    if "pid" in doc:
         return str(doc["pid"])
    return id_val


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _validate_variant(config: EvalConfig, retrieval_meta: dict[str, Any]) -> str | None:
    variant = config.variant
    retrieval_mode = str(retrieval_meta.get("retrieval_mode") or "")
    vector_backend = str(retrieval_meta.get("vector_backend") or "")

    if "official" in config.tags and vector_backend == "mock_milvus":
        return "official eval cannot use mock_milvus backend"
    if variant == "dense_only" and retrieval_mode not in {"dense", "dense_fallback", "failed"}:
        return f"variant dense_only is not supported by current backend mode={retrieval_mode}"
    if variant == "sparse_only" and retrieval_mode not in {"sparse", "failed"}:
        return f"variant sparse_only is not supported by current backend mode={retrieval_mode}"
    return None


def run_eval(config: EvalConfig, dataset_path: Path, sample_limit: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from rag_utils import retrieve_documents

    rows = _load_jsonl(dataset_path)
    if sample_limit:
        rows = rows[:sample_limit]
        print(f"Sampling first {len(rows)} items from dataset.")
    sample_results = []
    params = dict(config.params or {})
    for row in rows:
        query_id = str(row.get("query_id") or row.get("id") or "")
        query = str(row.get("query_text") or row.get("question") or "")
        relevant = {str(item) for item in row.get("relevant_doc_ids", []) if str(item).strip()}

        started = time.perf_counter()
        retrieval = retrieve_documents(
            query,
            top_k=int(params.get("top_k", 10)),
            retrieval_mode=params.get("retrieval_mode"),
            rerank_enabled=params.get("rerank_enabled"),
            auto_merge_enabled=params.get("auto_merge_enabled"),
            candidate_k=params.get("candidate_k"),
            leaf_retrieve_level=params.get("leaf_retrieve_level"),
            auto_merge_threshold=params.get("auto_merge_threshold"),
        )
        latency_ms = (time.perf_counter() - started) * 1000

        docs = retrieval.get("docs", [])
        meta = retrieval.get("meta", {})
        predicted = _dedupe_preserve_order([_doc_id(doc) for doc in docs if _doc_id(doc)])
        variant_error = _validate_variant(config, meta)

        sample_results.append(
            {
                "query_id": query_id,
                "dataset": config.dataset,
                "variant": config.variant,
                "query_text": query,
                "topk_doc_ids": predicted,
                "relevant_doc_ids": sorted(relevant),
                "recall_at_5": recall_at_k(predicted, relevant, 5),
                "recall_at_10": recall_at_k(predicted, relevant, 10),
                "mrr_at_10": round(mrr_at_k(predicted, relevant, 10), 6),
                "ndcg_at_10": round(ndcg_at_k(predicted, relevant, 10), 6),
                "retrieval_latency_ms": round(latency_ms, 2),
                "retrieval_mode": meta.get("retrieval_mode"),
                "vector_backend": meta.get("vector_backend"),
                "status": "unsupported" if variant_error else "ok",
                "error": variant_error,
            }
        )

    summary = {
        "dataset": config.dataset,
        "variant": config.variant,
        "config_hash": config_hash(config.to_dict()),
        "generated_at": _utc_now(),
        "sample_count": len(sample_results),
        "supported_sample_count": sum(1 for row in sample_results if row["status"] == "ok"),
        "nonempty_result_count": sum(1 for row in sample_results if row["topk_doc_ids"]),
        "recall_at_5": safe_mean(row["recall_at_5"] for row in sample_results if row["status"] == "ok"),
        "recall_at_10": safe_mean(row["recall_at_10"] for row in sample_results if row["status"] == "ok"),
        "mrr_at_10": safe_mean(row["mrr_at_10"] for row in sample_results if row["status"] == "ok"),
        "ndcg_at_10": safe_mean(row["ndcg_at_10"] for row in sample_results if row["status"] == "ok"),
        "avg_retrieval_latency_ms": safe_mean(row["retrieval_latency_ms"] for row in sample_results if row["status"] == "ok"),
    }
    return sample_results, summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run retrieval eval against a normalized JSONL dataset.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset-path", type=Path, required=True)
    parser.add_argument("--sample-limit", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = EvalConfig.from_mapping(load_config_file(args.config))
    rows, summary = run_eval(config, args.dataset_path, args.sample_limit)
    writer = ResultBundleWriter(Path(config.output_dir))
    writer.write(
        prefix=config.variant,
        records=rows,
        metadata={"config": config.snapshot(), "summary": summary},
        summary="# Retrieval Eval\n\nGenerated sample-level retrieval metrics.\n",
        table_columns=[
            "query_id",
            "variant",
            "recall_at_5",
            "recall_at_10",
            "mrr_at_10",
            "ndcg_at_10",
            "retrieval_latency_ms",
            "status",
            "error",
        ],
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if "official" in config.tags and summary.get("supported_sample_count", 0) == 0:
        print("official retrieval eval produced zero supported samples", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
