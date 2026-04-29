from __future__ import annotations

import argparse
import sys
from pathlib import Path
import json
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
DEFAULT_LOTTE_ROOT = REPO_ROOT / "eval" / "datasets" / "lotte" / "lotte"
DEFAULT_NORMALIZED_ROOT = REPO_ROOT / "eval" / "datasets" / "lotte" / "normalized"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from document_loader import DocumentLoader
from embedding import EmbeddingService
from milvus_client import MilvusManager
from milvus_writer import MilvusWriter
from parent_chunk_store import ParentChunkStore
import time


def _default_queries_path(domain: str, split: str, query_set: str) -> Path:
    return DEFAULT_NORMALIZED_ROOT / domain / f"{split}.{query_set}.jsonl"


def _default_collection_path(domain: str, split: str) -> Path:
    return DEFAULT_LOTTE_ROOT / domain / split / "collection.tsv"


def _iter_relevant_pids(path: Path, query_limit: int | None = None) -> Iterable[str]:
    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            if query_limit is not None and idx > query_limit:
                break
            row = json.loads(line)
            for pid in row.get("relevant_doc_ids", []):
                pid_str = str(pid).strip()
                if pid_str:
                    yield pid_str


def parse_args():
    parser = argparse.ArgumentParser(description="Ingest LoTTE collection with sampling.")
    parser.add_argument("--domain", type=str, default="technology")
    parser.add_argument("--split", type=str, default="dev")
    parser.add_argument("--query-set", type=str, choices=("forum", "search"), default="forum")
    parser.add_argument("--queries-path", type=Path, help="Path to normalized queries to extract relevant pids.")
    parser.add_argument("--collection-path", type=Path, help="Path to LoTTE collection.tsv.")
    parser.add_argument("--distractor-limit", type=int, default=5000, help="Number of distractors to ingest.")
    parser.add_argument("--batch-size", type=int, default=8, help="Writer batch size for leaf chunks.")
    parser.add_argument("--sleep-seconds", type=float, default=1.0, help="Delay between write batches.")
    parser.add_argument("--max-required-pids", type=int, default=None, help="Optional cap for relevant PIDs to ingest.")
    parser.add_argument("--query-limit", type=int, default=None, help="Only scan the first N query rows when collecting relevant PIDs.")
    parser.add_argument("--skip-parent-store", action="store_true", help="Skip parent chunk upserts. Useful for dense-only pilots.")
    return parser.parse_args()

def main():
    args = parse_args()
    queries_path = args.queries_path or _default_queries_path(args.domain, args.split, args.query_set)
    collection_path = args.collection_path or _default_collection_path(args.domain, args.split)
    
    # 1. Identify required PIDs from queries
    required_pids = set()
    if queries_path.exists():
        for pid in _iter_relevant_pids(queries_path, query_limit=args.query_limit):
            required_pids.add(pid)
            if args.max_required_pids is not None and len(required_pids) >= args.max_required_pids:
                break
    else:
        raise FileNotFoundError(f"Queries path not found: {queries_path}")

    if not collection_path.exists():
        raise FileNotFoundError(f"Collection path not found: {collection_path}")

    print(f"Required PIDs from queries: {len(required_pids)}")
    print(f"Using collection: {collection_path}")
    print(f"Using query set: {args.query_set}")

    # 2. Setup ingestion stack
    loader = DocumentLoader()
    parent_store = None if args.skip_parent_store else ParentChunkStore()
    milvus_manager = MilvusManager()
    embedding_service = EmbeddingService()
    writer = MilvusWriter(embedding_service=embedding_service, milvus_manager=milvus_manager)

    # 3. Process collection.tsv
    count = 0
    distractors_added = 0
    ingested_count = 0
    
    # Get existing PIDs for resume support
    existing_pids = set()
    try:
        results = milvus_manager.query(output_fields=["pid"])
        existing_pids = {r["pid"] for r in results if "pid" in r}
        print(f"Found {len(existing_pids)} existing PIDs in storage.")
    except Exception as e:
        print(f"Could not fetch existing PIDs: {e}")

    # 4. Pre-scan for texts to fit BM25 once (Optimization)
    print("Pre-scanning collection to optimize BM25 fitting...")
    all_new_texts = []
    to_ingest = []
    
    with open(collection_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t", 1)
            if len(parts) < 2: continue
            pid, text = parts
            
            is_required = pid in required_pids
            if not is_required and distractors_added >= args.distractor_limit:
                continue
                
            if pid in existing_pids:
                if is_required: ingested_count += 1
                else: distractors_added += 1
                count += 1
                continue
            
            all_new_texts.append(text)
            to_ingest.append((pid, text, is_required))
            if not is_required:
                distractors_added += 1
            else:
                ingested_count += 1
            count += 1

    if all_new_texts:
        print(f"Fitting embedding service on {len(all_new_texts)} new texts...")
        # Get existing texts to maintain global context
        try:
            existing_docs = milvus_manager.query(filter_expr="chunk_level == 3", output_fields=["text"], limit=100000)
            existing_texts = [item.get("text", "") for item in existing_docs if item.get("text")]
        except Exception as e:
            print(f"Could not fetch existing texts for BM25 bootstrap: {e}")
            existing_texts = []
        embedding_service.fit_corpus(existing_texts + all_new_texts)
        embedding_service.save_state()

    # 5. Batch Ingest
    batch_size = max(1, int(args.batch_size))
    for i in range(0, len(to_ingest), batch_size):
        batch_items = to_ingest[i:i+batch_size]
        all_leaf_chunks = []
        
        for pid, text, is_required in batch_items:
            filename = f"lotte_{pid}"
            chunks = loader.load_text(text, filename, {"pid": pid, "domain": args.domain})
            
            parent_chunks = [c for c in chunks if c["chunk_level"] in (1, 2)]
            leaf_chunks = [c for c in chunks if c["chunk_level"] == 3]
            
            if parent_store is not None and parent_chunks:
                parent_store.upsert_documents(parent_chunks)
            if leaf_chunks:
                all_leaf_chunks.extend(leaf_chunks)
        
        if all_leaf_chunks:
            # Using same batch_size for writer to remain consistent
            writer.write_documents(all_leaf_chunks, batch_size=batch_size)
            # Add a larger delay for API rate limit safety
            if args.sleep_seconds > 0:
                time.sleep(float(args.sleep_seconds))
        
        if (i // batch_size + 1) % 5 == 0:
            print(f"Processed batch {i//batch_size + 1}/{(len(to_ingest)-1)//batch_size + 1}...")

    print(f"Completed ingestion for LoTTE {args.domain}/{args.split}/{args.query_set}. Total processed in this run: {len(to_ingest)}")
    print(f"Completed ingestion for LoTTE {args.domain}/{args.split}/{args.query_set}. Total scanned lines: {count}")

if __name__ == "__main__":
    main()
