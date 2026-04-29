from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import dotenv_values


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _print_result(name: str, ok: bool, detail: str) -> None:
    status = "OK" if ok else "BLOCKED"
    print(f"[{status}] {name}: {detail}")


def _check_http(name: str, url: str, headers: dict[str, str] | None = None) -> tuple[bool, str]:
    try:
        response = requests.get(url, headers=headers, timeout=10)
        return True, f"HTTP {response.status_code} {url}"
    except Exception as exc:
        return False, f"{url} -> {exc!r}"


def _check_tcp(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"{host}:{port} reachable"
    except Exception as exc:
        return False, f"{host}:{port} -> {exc!r}"


def _milvus_ready() -> tuple[bool, str]:
    os.environ["MILVUS_REQUIRE_REAL"] = "true"
    try:
        from milvus_client import MilvusManager

        manager = MilvusManager()
        manager._get_client()
        return True, f"connected via {manager.uri}"
    except Exception as exc:
        return False, repr(exc)


def _sqlite_ready(database_url: str | None) -> tuple[bool, str]:
    if not database_url:
        return False, "DATABASE_URL missing"
    if not database_url.startswith("sqlite:///"):
        return True, database_url
    db_path = database_url.replace("sqlite:///", "", 1)
    resolved = (REPO_ROOT / db_path).resolve() if not Path(db_path).is_absolute() else Path(db_path)
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        with resolved.open("a", encoding="utf-8"):
            pass
        return True, str(resolved)
    except Exception as exc:
        return False, f"{resolved} -> {exc!r}"


def main() -> int:
    cfg: dict[str, Any] = dotenv_values(REPO_ROOT / ".env")
    blockers = 0

    milvus_uri = str(cfg.get("MILVUS_URI") or "")
    if not milvus_uri or not milvus_uri.startswith("http"):
        blockers += 1
        _print_result("Milvus URI", False, f"expected real service URI, got {milvus_uri or 'MISSING'}")
    else:
        _print_result("Milvus URI", True, milvus_uri)

    milvus_host = str(cfg.get("MILVUS_HOST") or "127.0.0.1")
    try:
        milvus_port = int(cfg.get("MILVUS_PORT") or 19530)
    except ValueError:
        milvus_port = 19530
    ok, detail = _check_tcp(milvus_host, milvus_port)
    if not ok:
        blockers += 1
    _print_result("Milvus TCP", ok, detail)

    ok, detail = _milvus_ready()
    if not ok:
        blockers += 1
    _print_result("Milvus Client", ok, detail)

    base_url = str(cfg.get("BASE_URL") or "").rstrip("/")
    if base_url:
        ok, detail = _check_http("Model Gateway", f"{base_url}/models")
        if not ok:
            blockers += 1
        _print_result("Model Gateway", ok, detail)
    else:
        blockers += 1
        _print_result("Model Gateway", False, "BASE_URL missing")

    embedding_base_url = str(cfg.get("EMBEDDING_BASE_URL") or "").rstrip("/")
    embedding_api_key = str(cfg.get("EMBEDDING_API_KEY") or "")
    if embedding_base_url and embedding_api_key:
        ok, detail = _check_http(
            "Embedding API",
            f"{embedding_base_url}/models",
            headers={"Authorization": f"Bearer {embedding_api_key}"},
        )
        _print_result("Embedding API", ok, detail)
    else:
        blockers += 1
        _print_result("Embedding API", False, "EMBEDDING_BASE_URL or EMBEDDING_API_KEY missing")

    rerank_host = str(cfg.get("RERANK_BINDING_HOST") or "").rstrip("/")
    rerank_api_key = str(cfg.get("RERANK_API_KEY") or "")
    if rerank_host and rerank_api_key:
        ok, detail = _check_http(
            "Rerank API",
            rerank_host,
            headers={"Authorization": f"Bearer {rerank_api_key}"},
        )
        _print_result("Rerank API", ok, detail)
    else:
        _print_result("Rerank API", False, "RERANK_BINDING_HOST or RERANK_API_KEY missing")

    redis_url = str(cfg.get("REDIS_URL") or "")
    if redis_url.startswith("redis://"):
        host_port = redis_url.replace("redis://", "", 1).split("/", 1)[0]
        host, _, port = host_port.partition(":")
        ok, detail = _check_tcp(host or "127.0.0.1", int(port or 6379))
        _print_result("Redis", ok, detail)
    else:
        _print_result("Redis", False, f"unexpected REDIS_URL={redis_url or 'MISSING'}")

    ok, detail = _sqlite_ready(str(cfg.get("DATABASE_URL") or ""))
    if not ok:
        blockers += 1
    _print_result("Database URL", ok, detail)

    if blockers:
        print(f"\nOfficial readiness check failed with {blockers} blocker(s).")
        return 2

    print("\nOfficial readiness check passed. Safe to start official eval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
