from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Mapping
from dataclasses import is_dataclass

try:
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    yaml = None


class ConfigError(ValueError):
    """Raised when an eval config cannot be loaded or validated."""


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return value.__dict__
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def config_hash(value: Any) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return digest[:12]


def load_config_text(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return {}

    if yaml is not None:
        try:
            return yaml.safe_load(stripped)
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise ConfigError("Failed to parse YAML config") from exc

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            "PyYAML is unavailable and the config is not valid JSON-compatible YAML"
        ) from exc


def load_config_file(path: str | Path) -> Any:
    path = Path(path)
    return load_config_text(path.read_text(encoding="utf-8"))


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = copy.deepcopy(dict(base))
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], Mapping)
            and isinstance(value, Mapping)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


@dataclass(slots=True)
class EvalConfig:
    name: str
    kind: str
    dataset: str
    variant: str
    seed: int = 42
    output_dir: str = "eval/outputs"
    params: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EvalConfig":
        missing = [key for key in ("name", "kind", "dataset", "variant") if key not in data]
        if missing:
            raise ConfigError(f"Missing required config keys: {', '.join(missing)}")
        params = dict(data.get("params") or {})
        tags = list(data.get("tags") or [])
        return cls(
            name=str(data["name"]),
            kind=str(data["kind"]),
            dataset=str(data["dataset"]),
            variant=str(data["variant"]),
            seed=int(data.get("seed", 42)),
            output_dir=str(data.get("output_dir", "eval/outputs")),
            params=params,
            tags=tags,
            notes=str(data.get("notes", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def snapshot(self) -> dict[str, Any]:
        data = self.to_dict()
        data["config_hash"] = config_hash(data)
        return data
