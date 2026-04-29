from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from embedding import EmbeddingService


def main() -> int:
    service = EmbeddingService()
    texts = [
        "hello world",
        "How do I add new styles to Google docs?",
    ]
    vectors = service.get_embeddings(texts)
    dim = len(vectors[0]) if vectors else 0
    print({"count": len(vectors), "dim": dim})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
