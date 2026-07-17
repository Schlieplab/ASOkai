#!/usr/bin/env python
"""Publish CWL-owned output files into their declared relative hierarchy."""
from __future__ import annotations

import errno
import logging
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

import yaml


logger = logging.getLogger(__name__)
PUBLISHED_DIR = "published"


@dataclass(frozen=True)
class PublicationEntry:
    """One workflow output and its destination below the data directory."""

    output_id: str
    destination: PurePosixPath

    def __post_init__(self) -> None:
        destination = PurePosixPath(self.destination)
        if (
            destination.is_absolute()
            or not destination.parts
            or ".." in destination.parts
        ):
            raise ValueError(
                f"Publication destination must stay below datadir: {destination!s}."
            )
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", destination.parts[0]):
            raise ValueError(
                "Publication root must contain only letters, numbers, dots, "
                f"underscores, and hyphens: {destination.parts[0]!r}."
            )
        object.__setattr__(self, "destination", destination)

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.output_id,
            "destination": self.destination.as_posix(),
        }


@dataclass(frozen=True)
class PublicationPlan:
    """Ordered publication metadata shared by CWL generation and execution."""

    entries: tuple[PublicationEntry, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))
        output_ids = [entry.output_id for entry in self.entries]
        destinations = [entry.destination for entry in self.entries]
        self._require_unique("output id", output_ids)
        self._require_unique("destination", destinations)
        for index, destination in enumerate(destinations):
            for other in destinations[index + 1:]:
                shorter, longer = sorted(
                    (destination, other),
                    key=lambda value: len(value.parts),
                )
                if longer.parts[:len(shorter.parts)] == shorter.parts:
                    raise ValueError(
                        "Publication destinations cannot contain one another: "
                        f"{shorter} and {longer}."
                    )

    @staticmethod
    def _require_unique(label: str, values: list[Any]) -> None:
        duplicates = sorted(
            {value for value in values if values.count(value) > 1},
            key=str,
        )
        if duplicates:
            joined = ", ".join(str(value) for value in duplicates)
            raise ValueError(f"Duplicate publication {label}(s): {joined}.")

    @property
    def roots(self) -> tuple[str, ...]:
        """Return top-level destination names in first-seen order."""
        return tuple(dict.fromkeys(entry.destination.parts[0] for entry in self.entries))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "outputs": [entry.to_dict() for entry in self.entries],
        }

    def render(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False)

    @classmethod
    def from_dict(cls, data: Any) -> PublicationPlan:
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("Publication manifest must declare version: 1.")
        raw_outputs = data.get("outputs")
        if not isinstance(raw_outputs, list):
            raise ValueError("Publication manifest 'outputs' must be a list.")

        entries: list[PublicationEntry] = []
        for index, item in enumerate(raw_outputs):
            if not isinstance(item, dict):
                raise ValueError(f"Publication output {index} must be a mapping.")
            output_id = item.get("id")
            destination = item.get("destination")
            if not isinstance(output_id, str) or not output_id:
                raise ValueError(f"Publication output {index} has no valid id.")
            if not isinstance(destination, str) or not destination:
                raise ValueError(
                    f"Publication output '{output_id}' has no valid destination."
                )
            entries.append(PublicationEntry(output_id, PurePosixPath(destination)))
        return cls(tuple(entries))

    @classmethod
    def read(cls, path: Path) -> PublicationPlan:
        return cls.from_dict(yaml.safe_load(path.read_text(encoding="utf-8")))


_LINK_FALLBACK_ERRNOS = {
    errno.EXDEV,
    errno.EPERM,
    errno.EACCES,
    errno.EMLINK,
    errno.EINVAL,
    getattr(errno, "ENOTSUP", errno.EINVAL),
    getattr(errno, "EOPNOTSUPP", errno.EINVAL),
}


def _publish_file(source: Path, destination: Path) -> str:
    """Hard-link one file, falling back to an atomic copy when necessary."""
    resolved_source = source.resolve(strict=True)
    if not resolved_source.is_file():
        raise ValueError(f"Publication source is not a file: {source}.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(resolved_source, destination)
        return "linked"
    except OSError as exc:
        if exc.errno not in _LINK_FALLBACK_ERRNOS:
            raise

    temporary = destination.with_name(f".{destination.name}.asokai-tmp")
    try:
        shutil.copy2(resolved_source, temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return "copied"


def publish_outputs(
    manifest_path: Path,
    sources: Sequence[Path],
    *,
    workdir: Path | None = None,
) -> dict[str, Path]:
    """Publish ordered CWL inputs according to a validated manifest."""
    plan = PublicationPlan.read(manifest_path)
    if len(sources) != len(plan.entries):
        raise ValueError(
            "Publication source count does not match the manifest "
            f"({len(sources)} source(s), {len(plan.entries)} destination(s))."
        )

    publication_root = (workdir or Path.cwd()) / PUBLISHED_DIR
    published: dict[str, Path] = {}
    for source, entry in zip(sources, plan.entries, strict=True):
        destination = publication_root.joinpath(*entry.destination.parts)
        method = _publish_file(Path(source), destination)
        logger.info(
            "%s %s -> %s",
            method,
            entry.output_id,
            entry.destination,
        )
        published[entry.output_id] = destination
    return published
