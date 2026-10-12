#!/usr/bin/env python
"""
Filename: tests/unit/test_bowtie2.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for the Bowtie 2 command wrappers.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from ASOkai.Utils import (
    Bowtie2,
    Bowtie2Build,
    Bowtie2ExecutionError,
    Bowtie2Inspect,
)


@pytest.fixture
def executable(tmp_path: Path) -> Path:
    path = tmp_path / "bowtie2-tool"
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return path


def _success() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, "", "")


def test_missing_executable_reports_name():
    with pytest.raises(FileNotFoundError, match="missing-bowtie2-command"):
        Bowtie2("missing-bowtie2-command")


def test_build_uses_index_basename_and_build_options(
    executable: Path, tmp_path: Path
):
    reference = tmp_path / "genome.fa.gz"
    index = tmp_path / "index" / "genome"
    with patch("ASOkai.Utils._bowtie2.subprocess.run", return_value=_success()) as run:
        Bowtie2Build(str(executable)).run(
            reference,
            index,
            threads=4,
            large_index=True,
            offrate=4,
            quiet=True,
        )

    args = run.call_args.args[0]
    assert args == [
        str(executable), "-f", "--threads", "4", "--large-index",
        "--offrate", "4", "--quiet", str(reference), str(index),
    ]
    assert index.parent.is_dir()
    assert run.call_args.kwargs["capture_output"] is True


def test_align_short_fasta_queries_with_all_hits(executable: Path, tmp_path: Path):
    index = tmp_path / "genome"
    reads = tmp_path / "queries.fa"
    sam = tmp_path / "out" / "hits.sam"
    with patch("ASOkai.Utils._bowtie2.subprocess.run", return_value=_success()) as run:
        Bowtie2(str(executable)).run(
            index,
            sam,
            reads=reads,
            read_format="fasta",
            threads=6,
            seed_length=16,
            seed_mismatches=1,
            all_alignments=True,
        )

    args = run.call_args.args[0]
    assert args == [
        str(executable), "-x", str(index), "-U", str(reads), "-f",
        "--threads", "6", "-L", "16", "-N", "1", "-a",
        "-S", str(sam),
    ]
    assert sam.parent.is_dir()


def test_align_supports_paired_reads(executable: Path, tmp_path: Path):
    with patch("ASOkai.Utils._bowtie2.subprocess.run", return_value=_success()) as run:
        Bowtie2(str(executable)).run(
            tmp_path / "index",
            tmp_path / "out.sam",
            mate1=tmp_path / "r1.fq",
            mate2=tmp_path / "r2.fq",
            max_alignments=3,
        )

    args = run.call_args.args[0]
    assert args[args.index("-1") + 1] == str(tmp_path / "r1.fq")
    assert args[args.index("-2") + 1] == str(tmp_path / "r2.fq")
    assert args[args.index("-k") + 1] == "3"


def test_align_rejects_incomplete_read_specification(executable: Path, tmp_path: Path):
    aligner = Bowtie2(str(executable))
    with pytest.raises(ValueError, match="Supply reads or both"):
        aligner.run(tmp_path / "index", tmp_path / "out.sam", mate1=tmp_path / "r1")
    with pytest.raises(ValueError, match="exclusive"):
        aligner.run(
            tmp_path / "index", tmp_path / "out.sam", reads=tmp_path / "r",
            all_alignments=True, max_alignments=2,
        )
    with pytest.raises(ValueError, match="Supply reads or both"):
        aligner.run(
            tmp_path / "index", tmp_path / "out.sam",
            reads=tmp_path / "r", mate1=tmp_path / "r1", mate2=tmp_path / "r2",
        )
    with pytest.raises(ValueError, match="seed_mismatches"):
        aligner.run(
            tmp_path / "index", tmp_path / "out.sam",
            reads=tmp_path / "r", seed_mismatches=True,
        )


def test_inspect_requests_names(executable: Path, tmp_path: Path):
    with patch("ASOkai.Utils._bowtie2.subprocess.run", return_value=_success()) as run:
        Bowtie2Inspect(str(executable)).run(tmp_path / "genome", names=True)

    assert run.call_args.args[0] == [
        str(executable), "--names", str(tmp_path / "genome"),
    ]


def test_failed_command_preserves_status_and_stderr(executable: Path, tmp_path: Path):
    failed = subprocess.CompletedProcess([], 2, "", "invalid index")
    with patch("ASOkai.Utils._bowtie2.subprocess.run", return_value=failed):
        with pytest.raises(Bowtie2ExecutionError) as error:
            Bowtie2Inspect(str(executable)).run(tmp_path / "genome")

    assert error.value.returncode == 2
    assert error.value.stderr == "invalid index"
    assert error.value.cmd[0] == str(executable)
