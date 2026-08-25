"""Reusable, atomic persistence services for generated artifacts and context inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fantasy_football_2026.errors import StorageError


class ArtifactStore:
    """Read typed JSON inputs and atomically persist generated files."""

    def load_json(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StorageError(f"Could not read {path}: {error}") from error

    def load_object(self, path: Path) -> dict[str, Any]:
        payload = self.load_json(path)
        if not isinstance(payload, dict):
            raise StorageError(f"Expected an object in {path}.")
        return payload

    def write_json(self, path: Path, payload: Any) -> None:
        self.write_text(path, json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")

    def write_text(self, path: Path, content: str) -> None:
        self.write_bytes(path, content.encode("utf-8"))

    def write_bytes(self, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            temporary.write_bytes(content)
            temporary.replace(path)
        except OSError as error:
            raise StorageError(f"Could not write {path}: {error}") from error
        finally:
            temporary.unlink(missing_ok=True)


DEFAULT_STORE = ArtifactStore()


def load_json_object(path: Path) -> dict[str, Any]:
    """Compatibility-friendly functional facade for object-shaped JSON."""

    return DEFAULT_STORE.load_object(path)


def write_json(path: Path, payload: Any) -> None:
    DEFAULT_STORE.write_json(path, payload)


def write_text(path: Path, content: str) -> None:
    DEFAULT_STORE.write_text(path, content)
