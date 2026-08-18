"""Provenance: content hashing, dataset registration and run manifests.

The proposal commits to reproducibility and open science. That is only real if
every published number can be traced back to the exact bytes it came from, so
each pipeline stage writes a manifest recording input hashes, output hashes,
configuration, seed and library versions.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from omics_wbe.config import RESULTS_DIR

_CHUNK = 1 << 20


def sha256_file(path: str | Path) -> str:
    """SHA-256 of a file, read in chunks so a 140 MB CSV never lands in memory."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git_revision() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=Path(__file__).resolve().parent.parent,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _library_versions() -> dict[str, str]:
    versions: dict[str, str] = {"python": platform.python_version()}
    for name in ("numpy", "pandas", "sklearn", "scipy", "matplotlib"):
        try:
            versions[name] = __import__(name).__version__
        except Exception:  # pragma: no cover - a missing optional dep is not fatal
            versions[name] = "not-installed"
    return versions


@dataclass
class RunManifest:
    """Record of one pipeline stage.

    Built incrementally (``add_input`` / ``add_output`` / ``add_metric``) and
    written once with :meth:`write`.
    """

    stage: str
    config: dict[str, Any]
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.started_at = datetime.now(timezone.utc).isoformat()

    def add_input(self, label: str, path: str | Path) -> "RunManifest":
        p = Path(path)
        self.inputs[label] = f"{p}::{sha256_file(p) if p.exists() else 'MISSING'}"
        return self

    def add_output(self, label: str, path: str | Path) -> "RunManifest":
        p = Path(path)
        self.outputs[label] = f"{p}::{sha256_file(p) if p.exists() else 'MISSING'}"
        return self

    def add_metric(self, key: str, value: Any) -> "RunManifest":
        self.metrics[key] = value
        return self

    def note(self, text: str) -> "RunManifest":
        self.notes.append(text)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "git_revision": _git_revision(),
            "libraries": _library_versions(),
            "config": self.config,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "metrics": self.metrics,
            "notes": self.notes,
        }

    def write(self, directory: str | Path | None = None) -> Path:
        directory = Path(directory) if directory else RESULTS_DIR / "manifests"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.stage}.manifest.json"
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str))
        return path


def verify_manifest(manifest_path: str | Path) -> dict[str, list[str]]:
    """Re-hash the files a manifest claims and report drift.

    Returns ``ok`` / ``changed`` / ``missing`` label lists so a reviewer can
    check a published result still corresponds to the data on disk, rather than
    taking the manifest's word for it.
    """
    data = json.loads(Path(manifest_path).read_text())
    report: dict[str, list[str]] = {"ok": [], "changed": [], "missing": []}
    for section in ("inputs", "outputs"):
        for label, entry in data.get(section, {}).items():
            path_str, _, expected = entry.rpartition("::")
            path = Path(path_str)
            key = f"{section}.{label}"
            if not path.exists() or expected == "MISSING":
                report["missing"].append(key)
            elif sha256_file(path) == expected:
                report["ok"].append(key)
            else:
                report["changed"].append(key)
    return report


def summarise_iterable(values: Iterable[Any], limit: int = 12) -> list[Any]:
    """Deterministic, bounded summary of a set of values for manifests."""
    uniq = sorted({v for v in values if v is not None and v == v}, key=str)
    return uniq[:limit] + (["..."] if len(uniq) > limit else [])
