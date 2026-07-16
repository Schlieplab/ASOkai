#!/usr/bin/env python
"""Integration coverage for the CWL-only output publisher prototype."""

import errno
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
from unittest.mock import patch

import pytest

from ASOkai._cwl.publisher import (
    PublicationEntry,
    PublicationPlan,
    publish_outputs,
)


FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "cwl_publisher"


def _write_manifest(path: Path, destination: str = "root/result.txt") -> None:
    path.write_text(
        PublicationPlan(
            (PublicationEntry("step__result", PurePosixPath(destination)),)
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
    assert published == {"step__result": destination}
    assert destination.read_text() == "result"
    assert os.path.samefile(source, destination)


def test_publisher_copies_when_hard_links_cross_filesystems(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("result")
    manifest = tmp_path / "layout.yml"
    _write_manifest(manifest)
    workdir = tmp_path / "work"

    with patch("ASOkai._cwl.publisher.os.link", side_effect=OSError(errno.EXDEV, "cross-device")):
        publish_outputs(manifest, [source], workdir=workdir)

    destination = workdir / "published" / "root" / "result.txt"
    assert destination.read_text() == "result"
    assert not os.path.samefile(source, destination)


def test_publication_plan_rejects_duplicate_destinations():
    with pytest.raises(ValueError, match="Duplicate publication destination"):
        PublicationPlan(
            (
                PublicationEntry("first", PurePosixPath("root/result.txt")),
                PublicationEntry("second", PurePosixPath("root/result.txt")),
            )
        )


def test_publication_entry_rejects_parent_traversal():
    with pytest.raises(ValueError, match="stay below datadir"):
        PublicationEntry("result", PurePosixPath("../result.txt"))


def test_publication_plan_rejects_file_directory_collisions():
    with pytest.raises(ValueError, match="cannot contain one another"):
        PublicationPlan(
            (
                PublicationEntry("first", PurePosixPath("root/result")),
                PublicationEntry("second", PurePosixPath("root/result/nested.txt")),
            )
        )


@pytest.mark.skipif(shutil.which("cwltool") is None, reason="cwltool is not installed")
def test_cwl_publisher_merges_real_files_into_existing_tree(tmp_path):
    outdir = tmp_path / "data"
    existing = outdir / "GRCh38" / "existing" / "keep.txt"
    replaced = (
        outdir
        / "GRCh38"
        / "genomes"
        / "ensembl"
        / "114"
        / "Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz"
    )
    existing.parent.mkdir(parents=True)
    replaced.parent.mkdir(parents=True)
    existing.write_text("keep")
    replaced.write_text("old")

    result = subprocess.run(
        [
            "cwltool",
            "--outdir",
            str(outdir),
            str(FIXTURE_DIR / "run.cwl"),
            str(FIXTURE_DIR / "job.yml"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert existing.read_text() == "keep"
    assert replaced.read_text() == "dna"
    assert not replaced.is_symlink()

    target = (
        outdir
        / "GRCh38"
        / "targets"
        / "ENSG00000133703"
        / "ENSG00000133703_k16_pre-mrna.json"
    )
    assert target.read_text() == "target"
    assert not target.is_symlink()
