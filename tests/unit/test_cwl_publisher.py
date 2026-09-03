#!/usr/bin/env python
"""
Filename: tests/unit/test_cwl_publisher.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Unit tests for CWL output publication contracts and file handling.
License: LGPL-3.0-or-later
"""

import errno
import os
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import pytest

from ASOkai._cwl.publisher import (
    PublicationEntry,
    PublicationPlan,
    publish_outputs,
)

def _write_manifest(path: Path, destination: str = "root/result.txt") -> None:
    path.write_text(
        PublicationPlan(
            (PublicationEntry("step.result", PurePosixPath(destination)),)
        ).render()
    )


def test_publisher_uses_a_hard_link_when_supported(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("result")
    manifest = tmp_path / "layout.yml"
    _write_manifest(manifest)
    workdir = tmp_path / "work"

    published = publish_outputs(manifest, [source], workdir=workdir)

    destination = workdir / "published" / "root" / "result.txt"
    assert published == {"step.result": destination}
    assert destination.read_text() == "result"
    assert os.path.samefile(source, destination)


@pytest.mark.parametrize("link_errno", [errno.EXDEV, errno.ENOSYS])
def test_publisher_copies_when_hard_links_are_unavailable(tmp_path, link_errno):
    source = tmp_path / "source.txt"
    source.write_text("result")
    manifest = tmp_path / "layout.yml"
    _write_manifest(manifest)
    workdir = tmp_path / "work"

    with patch(
        "ASOkai._cwl.publisher.os.link",
        side_effect=OSError(link_errno, "hard link unavailable"),
    ):
        publish_outputs(manifest, [source], workdir=workdir)

    destination = workdir / "published" / "root" / "result.txt"
    assert destination.read_text() == "result"
    assert not os.path.samefile(source, destination)


@pytest.mark.parametrize(
    "destination",
    [
        "/absolute/result.txt",
        "../result.txt",
        "root/../result.txt",
        r"root\..\result.txt",
        "root/C:/result.txt",
    ],
)
def test_publication_entry_rejects_nonportable_or_escaping_paths(destination):
    with pytest.raises(ValueError, match="stay below datadir"):
        PublicationEntry("result", PurePosixPath(destination))


@pytest.mark.parametrize("output_id", ["", " "])
def test_publication_entry_rejects_blank_output_ids(output_id):
    with pytest.raises(ValueError, match="nonblank string"):
        PublicationEntry(output_id, PurePosixPath("root/result.txt"))


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ((), "at least one output"),
        (
            (
                PublicationEntry("result", PurePosixPath("first.txt")),
                PublicationEntry("result", PurePosixPath("second.txt")),
            ),
            "Duplicate publication output id",
        ),
        (
            (
                PublicationEntry("first", PurePosixPath("root/result.txt")),
                PublicationEntry("second", PurePosixPath("root/result.txt")),
            ),
            "Duplicate publication destination",
        ),
        (
            (
                PublicationEntry("first", PurePosixPath("root/result")),
                PublicationEntry(
                    "second",
                    PurePosixPath("root/result/nested.txt"),
                ),
            ),
            "cannot contain one another",
        ),
    ],
)
def test_publication_plan_rejects_invalid_entry_sets(entries, message):
    with pytest.raises(ValueError, match=message):
        PublicationPlan(entries)


def test_publication_manifest_rejects_boolean_version():
    with pytest.raises(ValueError, match="version: 1"):
        PublicationPlan.from_dict({"version": True, "outputs": []})


def test_publication_manifest_reports_malformed_yaml(tmp_path):
    manifest = tmp_path / "layout.yml"
    manifest.write_text("version: 1\noutputs: [", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid publication manifest"):
        PublicationPlan.read(manifest)


def test_publisher_rejects_source_count_before_creating_workspace(tmp_path):
    manifest = tmp_path / "layout.yml"
    _write_manifest(manifest)
    workdir = tmp_path / "work"

    with pytest.raises(ValueError, match="source count"):
        publish_outputs(manifest, [], workdir=workdir)

    assert not (workdir / "published").exists()


def test_publisher_removes_incomplete_workspace_after_failure(tmp_path):
    manifest = tmp_path / "layout.yml"
    manifest.write_text(
        PublicationPlan(
            (
                PublicationEntry("first", PurePosixPath("root/first.txt")),
                PublicationEntry("second", PurePosixPath("root/second.txt")),
            )
        ).render(),
        encoding="utf-8",
    )
    source = tmp_path / "first.txt"
    source.write_text("first", encoding="utf-8")
    workdir = tmp_path / "work"

    with pytest.raises(FileNotFoundError):
        publish_outputs(
            manifest,
            [source, tmp_path / "missing.txt"],
            workdir=workdir,
        )

    assert not (workdir / "published").exists()


def test_publisher_refuses_an_existing_workspace(tmp_path):
    manifest = tmp_path / "layout.yml"
    _write_manifest(manifest)
    source = tmp_path / "source.txt"
    source.write_text("result", encoding="utf-8")
    existing = tmp_path / "work/published/keep.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        publish_outputs(manifest, [source], workdir=tmp_path / "work")

    assert existing.read_text(encoding="utf-8") == "keep"
