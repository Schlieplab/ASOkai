#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/output_receipts.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Persistent validation receipts for generated step outputs.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import Any

from ASOkai._pipeline.contracts.execution import StepRun, StepRunOutput


_RECEIPT_VERSION = 1
_SIGNATURE_PATTERN = re.compile(r"[0-9a-f]{64}")


def _canonical_digest(value: Any) -> str:
    """Return a deterministic SHA-256 digest for JSON-compatible data."""
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _absolute_without_resolving(path: Path) -> Path:
    """Return an absolute lexical path without following symbolic links."""
    return Path(os.path.abspath(path))


def _datadir(run: StepRun) -> Path:
    """Return the absolute data directory for one concrete run."""
    return _absolute_without_resolving(Path(run.config["datadir"]))


def _relative_output_paths(run: StepRun) -> list[dict[str, str]]:
    """Return ordered output destinations relative to the data directory."""
    datadir = _datadir(run)
    return [
        {
            "name": output.name,
            "path": _absolute_without_resolving(
                run.output_path(output)
            ).relative_to(datadir).as_posix(),
        }
        for output in run.step.spec.outputs
    ]


def _file_metadata(path: Path) -> dict[str, int]:
    """Return metadata that changes with ordinary file or directory edits."""
    if path.is_dir():
        digest = hashlib.sha256()
        size = 0
        for entry in sorted(path.rglob("*")):
            stat = entry.stat()
            relative = entry.relative_to(path).as_posix()
            digest.update(
                f"{relative}\0{stat.st_mode}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode()
            )
            if entry.is_file():
                size += stat.st_size
        return {
            "size": size,
            # Keep the receipt shape stable; for directories this field is a
            # fingerprint of the contained paths and their file metadata.
            "mtime_ns": int.from_bytes(digest.digest()[:8], "big"),
        }
    stat = path.stat()
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _run_identity(run: StepRun) -> dict[str, Any]:
    """Return the stable, result-affecting identity of one configured run."""
    inputs: list[dict[str, Any]] = []
    for binding in run.inputs:
        source = binding.source
        if isinstance(source, Path):
            inputs.append(
                {
                    "name": binding.file_input.name,
                    "source": "override",
                    "path": str(source),
                    # This identifies the override used by the run; it is not
                    # a validation receipt for the external file.
                    **_file_metadata(source),
                }
            )
            continue

        assert isinstance(source, StepRunOutput)
        inputs.append(
            {
                "name": binding.file_input.name,
                "source": "producer",
                "producer": _run_signature(source.run),
                "output": source.output.name,
            }
        )

    step_type = type(run.step)
    return {
        "step": run.step.name,
        "step_type": f"{step_type.__module__}.{step_type.__qualname__}",
        "parameters": list(run.parameters.items()),
        "inputs": inputs,
    }


def _run_signature(run: StepRun) -> str:
    """Return the persistent signature for one configured computation."""
    return _canonical_digest(_run_identity(run))


def receipt_path(run: StepRun) -> Path:
    """Return the receipt location selected by a run's output destinations."""
    receipt_id = _canonical_digest(
        {
            "step": run.step.name,
            "outputs": _relative_output_paths(run),
        }
    )
    return (
        _datadir(run)
        / ".asokai"
        / "validation"
        / f"{run.step.name}-{receipt_id}.json"
    )


def _receipt_data(run: StepRun) -> dict[str, Any]:
    """Return current receipt data for a complete output set."""
    datadir = _datadir(run)
    outputs = []
    output_types = {
        output.name: output.file_type.cwl_type
        for output in run.step.spec.outputs
    }
    for declared in _relative_output_paths(run):
        path = datadir.joinpath(*PurePosixPath(declared["path"]).parts)
        expected = output_types[declared["name"]]
        if not (path.is_dir() if expected == "Directory" else path.is_file()):
            raise FileNotFoundError(path)
        outputs.append(
            {
                **declared,
                **_file_metadata(path),
            }
        )
    return {
        "version": _RECEIPT_VERSION,
        "run_signature": _run_signature(run),
        "outputs": outputs,
    }


def _has_receipt_shape(value: Any) -> bool:
    """Return whether decoded JSON has the exact receipt field types."""
    if not isinstance(value, dict) or set(value) != {
        "version",
        "run_signature",
        "outputs",
    }:
        return False
    if type(value["version"]) is not int or value["version"] != _RECEIPT_VERSION:
        return False
    if (
        type(value["run_signature"]) is not str
        or _SIGNATURE_PATTERN.fullmatch(value["run_signature"]) is None
    ):
        return False
    outputs = value["outputs"]
    if not isinstance(outputs, list) or not outputs:
        return False
    return all(
        isinstance(output, dict)
        and set(output) == {"name", "path", "size", "mtime_ns"}
        and type(output["name"]) is str
        and type(output["path"]) is str
        and type(output["size"]) is int
        and output["size"] >= 0
        and type(output["mtime_ns"]) is int
        and output["mtime_ns"] >= 0
        for output in outputs
    )


def reusable_output_paths(run: StepRun) -> dict[str, Path] | None:
    """Return unchanged receipted outputs, or ``None`` when execution is needed."""
    path = receipt_path(run)
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        current = _receipt_data(run)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    if not _has_receipt_shape(receipt) or receipt != current:
        return None
    return run.output_paths()


def record_validated_outputs(run: StepRun) -> Path:
    """Atomically record outputs validated by their successful producer."""
    path = receipt_path(run)
    data = _receipt_data(run)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            temporary = Path(stream.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path
