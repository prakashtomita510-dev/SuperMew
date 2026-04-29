from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from document_loader import DocumentLoader  # noqa: E402
from embedding import EmbeddingService  # noqa: E402
from milvus_client import MilvusManager  # noqa: E402
from milvus_writer import MilvusWriter  # noqa: E402
from parent_chunk_store import ParentChunkStore  # noqa: E402


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _stable_doc_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest normalized RAGBench context docs into the current Milvus collection.")
    parser.add_argument("--dataset-path", type=Path, required=True, help="Path to normalized RAGBench JSONL.")
    parser.add_argument("--subset", type=str, default="techqa", help="Subset label used in synthetic filenames.")
    parser.add_argument("--sample-limit", type=int, default=None, help="Only use the first N samples from the JSONL.")
    parser.add_argument("--max-docs", type=int, default=None, help="Optional cap on unique context docs to ingest.")
    parser.add_argument("--batch-size", type=int, default=8, help="Writer batch size for leaf chunks.")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Delay between write batches.")
    parser.add_argument("--skip-parent-store", action="store_true", help="Skip parent chunk upserts when the official DB is read-only.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dataset_path: Path = args.dataset_path
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset path not found: {dataset_path}")

    rows = _load_jsonl(dataset_path)
    if args.sample_limit is not None:
        rows = rows[: max(0, int(args.sample_limit))]
    if not rows:
        print("no rows selected")
        return 0

    unique_docs: list[tuple[str, str]] = []
    seen_doc_ids: set[str] = set()
    for row in rows:
        for text in row.get("context_docs") or []:
            doc_text = str(text or "").strip()
            if not doc_text:
                continue
            doc_id = _stable_doc_id(doc_text)
            if doc_id in seen_doc_ids:
                continue
            seen_doc_ids.add(doc_id)
            unique_docs.append((doc_id, doc_text))
            if args.max_docs is not None and len(unique_docs) >= int(args.max_docs):
                break
        if args.max_docs is not None and len(unique_docs) >= int(args.max_docs):
            break

    if not unique_docs:
        print("no context docs found")
        return 0

    loader = DocumentLoader()
    parent_store = None if args.skip_parent_store else ParentChunkStore()
    milvus_manager = MilvusManager()
    embedding_service = EmbeddingService()
    writer = MilvusWriter(embedding_service=embedding_service, milvus_manager=milvus_manager)

    milvus_manager.init_collection(dense_dim=embedding_service.get_output_dim())

    existing_filenames = set()
    try:
        existing_rows = milvus_manager.query(output_fields=["filename"], limit=100000)
        existing_filenames = {
            str(item.get("filename") or "").strip()
            for item in existing_rows
            if str(item.get("filename") or "").strip()
        }
    except Exception as exc:
        print(f"could not fetch existing filenames: {exc}")

    to_ingest: list[tuple[str, str]] = []
    for doc_id, text in unique_docs:
        filename = f"ragbench_{args.subset}_{doc_id}"
        if filename in existing_filenames:
            continue
        to_ingest.append((filename, text))

    print(
        json.dumps(
            {
                "selected_samples": len(rows),
                "unique_context_docs": len(unique_docs),
                "pending_docs": len(to_ingest),
                "subset": args.subset,
                "dataset_path": str(dataset_path),
            },
            ensure_ascii=False,
        )
    )

    if not to_ingest:
        print("all selected context docs already ingested")
        return 0

    batch_size = max(1, int(args.batch_size))
    total_parent = 0
    total_leaf = 0
    total_docs = 0
    for offset in range(0, len(to_ingest), batch_size):
        batch = to_ingest[offset : offset + batch_size]
        parent_docs: list[dict[str, Any]] = []
        leaf_docs: list[dict[str, Any]] = []

        for filename, text in batch:
            metadata = {
                "pid": filename,
                "subset": args.subset,
                "file_path": f"ragbench://{args.subset}/{filename}",
            }
            chunks = loader.load_text(text, filename, metadata)
            parent_docs.extend(doc for doc in chunks if int(doc.get("chunk_level", 0) or 0) in (1, 2))
            leaf_docs.extend(doc for doc in chunks if int(doc.get("chunk_level", 0) or 0) == 3)
            total_docs += 1

        if parent_store is not None and parent_docs:
            total_parent += parent_store.upsert_documents(parent_docs)
        if leaf_docs:
            writer.write_documents(leaf_docs, batch_size=batch_size)
            total_leaf += len(leaf_docs)

        batch_no = offset // batch_size + 1
        batch_total = (len(to_ingest) - 1) // batch_size + 1
        print(
            json.dumps(
                {
                    "batch": batch_no,
                    "batch_total": batch_total,
                    "docs_processed": total_docs,
                    "parent_chunks": total_parent,
                    "leaf_chunks": total_leaf,
                },
                ensure_ascii=False,
            )
        )
        if args.sleep_seconds > 0:
            time.sleep(float(args.sleep_seconds))

    print(
        json.dumps(
            {
                "status": "ok",
                "subset": args.subset,
                "dataset_path": str(dataset_path),
                "docs_ingested": total_docs,
                "parent_chunks": total_parent,
                "leaf_chunks": total_leaf,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
