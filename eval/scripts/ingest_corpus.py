from __future__ import annotations

import argparse
from pathlib import Path
import sys


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest a local document corpus into the current RAG stack.")
    parser.add_argument("--source-dir", type=Path, default=REPO_ROOT / "data" / "documents")
    parser.add_argument("--glob", type=str, default="*")
    parser.add_argument("--skip-parent-store", action="store_true", help="Skip parent chunk upserts when the DB is read-only.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_dir: Path = args.source_dir
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    loader = DocumentLoader()
    parent_store = None if args.skip_parent_store else ParentChunkStore()
    milvus_manager = MilvusManager()
    embedding_service = EmbeddingService()
    writer = MilvusWriter(embedding_service=embedding_service, milvus_manager=milvus_manager)

    files = [path for path in source_dir.glob(args.glob) if path.is_file()]
    if not files:
        print(f"no files matched in {source_dir}")
        return 0

    total_leaf = 0
    total_parent = 0
    supported_extensions = {".pdf", ".txt", ".docx", ".md"}
    for path in files:
        if path.suffix.lower() not in supported_extensions:
            print(f"Skipping unsupported file: {path.name}")
            continue
        try:
            docs = loader.load_document(str(path), path.name)
            parent_docs = [doc for doc in docs if int(doc.get("chunk_level", 0) or 0) in (1, 2)]
            leaf_docs = [doc for doc in docs if int(doc.get("chunk_level", 0) or 0) == 3]
            if parent_store is not None:
                parent_store.upsert_documents(parent_docs)
            writer.write_documents(leaf_docs)
            total_parent += 0 if parent_store is None else len(parent_docs)
            total_leaf += len(leaf_docs)
            parent_label = "skipped" if parent_store is None else str(len(parent_docs))
            print(f"ingested {path.name}: parent={parent_label} leaf={len(leaf_docs)}")
        except Exception as e:
            print(f"Error ingesting {path.name}: {e}")
            continue

    print(f"completed ingestion: parent={total_parent} leaf={total_leaf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
