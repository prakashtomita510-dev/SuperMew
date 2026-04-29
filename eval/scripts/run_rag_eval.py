from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import time
import re
import csv
from typing import Any

from config import EvalConfig, config_hash, load_config_file
from metrics import exact_match, safe_mean, token_f1
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
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _score_answer(prediction: str, gold: str) -> dict[str, float]:
    scores = {
        "answer_accuracy_em": float(exact_match(prediction, gold)),
        "answer_accuracy_f1": round(token_f1(prediction, gold), 6),
    }
    
    # Optional Semantic Similarity
    try:
        from embedding import EmbeddingService
        import numpy as np
        svc = EmbeddingService()
        vecs = svc.get_embeddings([prediction, gold])
        v1 = np.array(vecs[0])
        v2 = np.array(vecs[1])
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 > 0 and norm2 > 0:
            sim = np.dot(v1, v2) / (norm1 * norm2)
            scores["answer_accuracy_semantic"] = round(float(sim), 6)
    except Exception as e:
        # Don't fail the whole eval if embedding similarity fails
        pass
        
    return scores


def _score_refusal(prediction: str, is_unanswerable: bool) -> bool | None:
    refusal_keywords = ["抱歉", "无法回答", "没有提及", "未提及", "不包含", "没有找到", "does not mention", "cannot answer", "sorry", "暂无相关信息"]
    is_refusal = any(kw in prediction.lower() for kw in refusal_keywords)
    
    if is_unanswerable:
        # Success if it refuses
        return is_refusal
    else:
        # Success if it DOES NOT refuse
        return not is_refusal

def _score_citations(prediction: str, rag_trace: dict, gold_spans: list) -> dict[str, float]:
    if not gold_spans:
        return {"citation_precision": 1.0, "citation_recall": 1.0}
    
    retrieved = rag_trace.get("retrieved_chunks", [])
    if not retrieved:
        return {"citation_precision": 0.0, "citation_recall": 0.0}

    # Identify which retrieved chunks are "gold" (contain at least one gold span)
    gold_indices = set()
    for i, chunk in enumerate(retrieved):
        content = chunk.get("content", "")
        for span in gold_spans:
            span_text = span.get("span_text", "").strip()
            if span_text and span_text in content:
                gold_indices.add(i)
                break
    
    matches = re.findall(r"\[(\d+)\]", prediction)
    cited_indices = set()
    for m in matches:
        idx = int(m) - 1
        if 0 <= idx < len(retrieved):
            cited_indices.add(idx)
    
    if not cited_indices:
        return {"citation_precision": 0.0, "citation_recall": 0.0 if gold_indices else 1.0}
        
    cited_gold = cited_indices.intersection(gold_indices)
    
    precision = len(cited_gold) / len(cited_indices) if cited_indices else 0.0
    recall = len(cited_gold) / len(gold_indices) if gold_indices else 1.0
    
    return {
        "citation_precision": round(precision, 4),
        "citation_recall": round(recall, 4)
    }

def _groundedness_from_trace(rag_trace: dict[str, Any] | None) -> float | None:
    if not rag_trace:
        return None
    score = str(rag_trace.get("hallucination_score") or "").lower().strip()
    if score == "yes":
        return 1.0
    if score == "no":
        return 0.0
    return None


def _validate_rag_sample(config: EvalConfig, rag_trace: dict[str, Any]) -> str | None:
    if "official" not in config.tags:
        return None

    if not rag_trace:
        return "official eval requires a non-empty rag_trace"

    vector_backend = str(rag_trace.get("vector_backend") or "")
    if not vector_backend:
        return "official eval requires vector_backend in rag_trace"
    if vector_backend == "mock_milvus":
        return "official eval cannot use mock_milvus backend"

    retrieval_mode = str(rag_trace.get("retrieval_mode") or "")
    if not retrieval_mode:
        return "official eval requires retrieval_mode in rag_trace"

    return None


def _apply_runtime_env(config: EvalConfig) -> None:
    params = config.params or {}

    rewrite_mode = params.get("rewrite_mode")
    if rewrite_mode is not None:
        os.environ["RAG_REWRITE_MODE"] = str(rewrite_mode)

    auto_merge_enabled = params.get("auto_merge_enabled")
    if auto_merge_enabled is not None:
        os.environ["AUTO_MERGE_ENABLED"] = "true" if bool(auto_merge_enabled) else "false"

    auto_merge_threshold = params.get("auto_merge_threshold")
    if auto_merge_threshold is not None:
        os.environ["AUTO_MERGE_THRESHOLD"] = str(auto_merge_threshold)

    leaf_retrieve_level = params.get("leaf_retrieve_level")
    if leaf_retrieve_level is not None:
        os.environ["LEAF_RETRIEVE_LEVEL"] = str(leaf_retrieve_level)

    hybrid_weights = params.get("hybrid_weights")
    if hybrid_weights is not None:
        if isinstance(hybrid_weights, list):
            os.environ["RAG_HYBRID_WEIGHTS"] = ",".join(map(str, hybrid_weights))
        else:
            os.environ["RAG_HYBRID_WEIGHTS"] = str(hybrid_weights)

    candidate_k = params.get("candidate_k")
    if candidate_k is not None:
        os.environ["RAG_CANDIDATE_K"] = str(candidate_k)

    rerank_enabled = params.get("rerank_enabled")
    if rerank_enabled is not None:
        os.environ["RAG_RERANK_ENABLED"] = "true" if bool(rerank_enabled) else "false"

    stream = params.get("stream")
    if stream is not None:
        os.environ["RAG_STREAM_ENABLED"] = "true" if bool(stream) else "false"


def run_eval(config: EvalConfig, dataset_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _apply_runtime_env(config)
    from rag_pipeline import run_rag_graph

    rows = _load_jsonl(dataset_path)
    sample_results = []
    total = len(rows)
    print(f"Starting eval for {config.variant} on {dataset_path.name} ({total} samples)...", flush=True)
    
    # Live CSV Logging Setup
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    live_csv_path = output_dir / f"live_results_{config.variant}.csv"
    live_csv_path = output_dir / f"live_results_{config.variant}.csv"
    csv_fields = ["question_id", "answer_accuracy_f1", "answer_accuracy_semantic", "groundedness_score", "citation_precision", "citation_recall", "is_refusal_correct", "latency_ms", "ttft_ms"]
    
    with open(live_csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=csv_fields)
        writer.writeheader()

    for i, row in enumerate(rows, 1):
        question_id = str(row.get("id") or row.get("sample_id") or "")
        print(f"[{i}/{total}] Processing {question_id}...", flush=True)
        question = str(row.get("question") or row.get("query_text") or "")
        gold_answer = str(row.get("gold_answer") or "")
        is_unanswerable = bool(row.get("is_unanswerable", False))
        gold_spans = row.get("gold_spans", [])
        started = time.perf_counter()
        
        # Execute with timeout to prevent hung samples from stalling the whole sweep
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_rag_graph, question)
            try:
                result = future.result(timeout=180) # 3 minute timeout
            except concurrent.futures.TimeoutError:
                print(f"⚠️ Timeout processing {question_id} after 180s. Skipping.")
                result = {"answer": "Error: Timeout", "rag_trace": {"status": "timeout"}}
            except Exception as e:
                print(f"⚠️ Error processing {question_id}: {e}")
                result = {"answer": f"Error: {e}", "rag_trace": {"status": "error", "error": str(e)}}

        duration_ms = (time.perf_counter() - started) * 1000
        prediction = str(result.get("answer") or "")
        rag_trace = result.get("rag_trace") or {}
        answer_scores = _score_answer(prediction, gold_answer) if gold_answer else {}
        groundedness = _groundedness_from_trace(rag_trace)
        sample_error = _validate_rag_sample(config, rag_trace)
        
        # New Metrics
        cit_scores = _score_citations(prediction, rag_trace, gold_spans)
        refusal_correct = _score_refusal(prediction, is_unanswerable)

        sample_data = {
            "question_id": question_id,
            "dataset": config.dataset,
            "variant": config.variant,
            "pred_answer": prediction,
            "gold_answer": gold_answer,
            "answer_accuracy": answer_scores.get("answer_accuracy_f1"),
            "answer_accuracy_em": answer_scores.get("answer_accuracy_em"),
            "answer_accuracy_semantic": answer_scores.get("answer_accuracy_semantic"),
            "groundedness_score": groundedness,
            "citation_precision": cit_scores.get("citation_precision"),
            "citation_recall": cit_scores.get("citation_recall"),
            "is_refusal_correct": refusal_correct,
            "generation_latency_ms": round(duration_ms, 2),
            "vector_backend": rag_trace.get("vector_backend"),
            "retrieval_mode": rag_trace.get("retrieval_mode"),
            "status": "unsupported" if sample_error else "ok",
            "error": sample_error,
            "rag_trace": rag_trace,
        }
        sample_results.append(sample_data)
        
        # Live append to CSV
        with open(live_csv_path, "a", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_fields)
            writer.writerow({
                "question_id": question_id,
                "answer_accuracy_f1": sample_data["answer_accuracy"],
                "answer_accuracy_semantic": sample_data["answer_accuracy_semantic"],
                "groundedness_score": sample_data["groundedness_score"],
                "citation_precision": sample_data["citation_precision"],
                "citation_recall": sample_data["citation_recall"],
                "is_refusal_correct": sample_data["is_refusal_correct"],
                "latency_ms": sample_data["generation_latency_ms"],
                "ttft_ms": rag_trace.get("stage_timings_ms", {}).get("ttft_ms")
            })

    summary = {
        "dataset": config.dataset,
        "variant": config.variant,
        "config_hash": config_hash(config.to_dict()),
        "generated_at": _utc_now(),
        "sample_count": len(sample_results),
        "supported_sample_count": sum(1 for row in sample_results if row["status"] == "ok"),
        "answer_accuracy": safe_mean(
            row["answer_accuracy"]
            for row in sample_results
            if row["status"] == "ok" and row.get("answer_accuracy") is not None
        ),
        "answer_accuracy_semantic": safe_mean(
            row["answer_accuracy_semantic"]
            for row in sample_results
            if row["status"] == "ok" and row.get("answer_accuracy_semantic") is not None
        ),
        "citation_precision": safe_mean(
            row["citation_precision"]
            for row in sample_results
            if row["status"] == "ok" and row.get("citation_precision") is not None
        ),
        "citation_recall": safe_mean(
            row["citation_recall"]
            for row in sample_results
            if row["status"] == "ok" and row.get("citation_recall") is not None
        ),
        "refusal_correctness_rate": safe_mean(
            float(row["is_refusal_correct"])
            for row in sample_results
            if row["status"] == "ok" and row.get("is_refusal_correct") is not None
        ),
        "groundedness_score": safe_mean(
            row["groundedness_score"]
            for row in sample_results
            if row["status"] == "ok" and row.get("groundedness_score") is not None
        ),
        "avg_generation_latency_ms": safe_mean(
            row["generation_latency_ms"] for row in sample_results if row["status"] == "ok"
        ),
    }
    return sample_results, summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run end-to-end RAG eval against a normalized JSONL dataset.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset-path", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = EvalConfig.from_mapping(load_config_file(args.config))
    rows, summary = run_eval(config, args.dataset_path)
    writer = ResultBundleWriter(Path(config.output_dir))
    writer.write(
        prefix=config.variant,
        records=rows,
        metadata={"config": config.snapshot(), "summary": summary},
        summary="# RAG Eval\n\nGenerated sample-level end-to-end answer metrics.\n",
        table_columns=[
            "question_id",
            "variant",
            "answer_accuracy",
            "groundedness_score",
            "generation_latency_ms",
            "retrieval_mode",
            "vector_backend",
            "status",
            "error",
        ],
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if "official" in config.tags and summary.get("supported_sample_count", 0) == 0:
        print("official rag eval produced zero supported samples", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
