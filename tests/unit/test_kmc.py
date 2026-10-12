#!/usr/bin/env python
"""
Filename: tests/unit/test_kmc.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for ASOkai.Utils.kmc (KMC and KMCExecutionError).
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from ASOkai.Utils import KMC, KMCExecutionError


@pytest.fixture
def fake_kmc(tmp_path: Path) -> Path:
    exe = tmp_path / "kmc"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    return exe


@pytest.fixture
def kmc(fake_kmc: Path) -> KMC:
    return KMC(str(fake_kmc))


def test_resolve_executable_missing() -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        KMC._resolve_executable("___not_a_real_kmc_binary___")


def test_kmc_run_minimal_args(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "in.fa"
    out = tmp_path / "out"
    work = tmp_path / "work"

    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils._kmc.subprocess.run", return_value=completed) as mock_run:
        kmc.run(inp, out, work, k=21, m=8, f="fm")

    argv = mock_run.call_args.args[0]
    assert argv[:4] == [kmc.executable, "-k21", "-m8", "-fm"]
    assert "-b" not in argv  # default b=False: canonical k-mers (no -b)


def test_kmc_run_b_true_disables_canonical(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "in.fa"
    out = tmp_path / "out"
    work = tmp_path / "work"

    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils._kmc.subprocess.run", return_value=completed) as mock_run:
        kmc.run(inp, out, work, k=21, m=8, f="fm", b=True)

    argv = mock_run.call_args.args[0]
    assert "-b" in argv


def test_kmc_run_canonical_off_and_flags(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "in.fa"
    out = tmp_path / "out"
    work = tmp_path / "work"

    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils._kmc.subprocess.run", return_value=completed) as mock_run:
        kmc.run(
            inp, out, work,
            k=16, m=12, f="fa",
            t=4, sm=True, hc=True,
            ci=1, cs=1024, cx=1000,
            b=False, r=True, n=10,
            o="kff",             j=Path("/tmp/summary.json"),
            hp=True, e=True,
            opt_out_size=True, v=True,
            additional_args=["--extra"],
        )

    argv = mock_run.call_args.args[0]
    assert "-v" in argv
    assert "-fa" in argv
    assert "-b" not in argv
    assert "-sm" in argv
    assert "-hc" in argv
    assert "-ci1" in argv
    assert "-cs1024" in argv
    assert "-cx1000" in argv
    assert "-okff" in argv
    assert "--extra" in argv
    assert any(a.startswith("-j") and "summary.json" in a for a in argv)


def test_kmc_run_treats_kff_suffix_as_the_output_file(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "in.fa"
    output = tmp_path / "index.kff"
    work = tmp_path / "work"

    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils._kmc.subprocess.run", return_value=completed) as mock_run:
        kmc.run(inp, output, work, o="kff")

    argv = mock_run.call_args.args[0]
    assert str(output.with_suffix("").resolve()) in argv
    assert str(output.resolve()) not in argv


def test_kmc_run_signature_length_invalid(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "in.fa"
    out = tmp_path / "out"
    work = tmp_path / "work"

    with pytest.raises(ValueError, match="between 5 and 11"):
        kmc.run(inp, out, work, p=4)

    with pytest.raises(ValueError, match="cannot be greater than k"):
        kmc.run(inp, out, work, k=7, p=9)


def test_run_rejects_k_out_of_range(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "in.fa"
    out, work = tmp_path / "out", tmp_path / "work"
    with pytest.raises(ValueError, match="k must be between"):
        kmc.run(inp, out, work, k=0)
    with pytest.raises(ValueError, match="k must be between"):
        kmc.run(inp, out, work, k=300)


def test_run_rejects_memory_gb_out_of_range(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "in.fa"
    out, work = tmp_path / "out", tmp_path / "work"
    with pytest.raises(ValueError, match="memory_gb"):
        kmc.run(inp, out, work, m=1)
    with pytest.raises(ValueError, match="memory_gb"):
        kmc.run(inp, out, work, m=2000)


def test_run_resolves_input_with_at_symbol(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "list.txt"
    out, work = tmp_path / "out", tmp_path / "work"

    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils._kmc.subprocess.run", return_value=completed) as mock_run:
        kmc.run(f"@{inp}", out, work)

    argv = mock_run.call_args.args[0]
    resolved_inp = [arg for arg in argv if arg.startswith("@")][0]
    assert resolved_inp == f"@{inp.resolve()}"


def test_run_creates_directories_and_invokes_subprocess(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "in.fa"
    inp.write_text(">a\nATCGATCGATCGATCG\n")
    out = tmp_path / "nested" / "dbprefix"
    work = tmp_path / "nested" / "scratch"

    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils._kmc.subprocess.run", return_value=completed) as mock_run:
        proc = kmc.run(inp, out, work, k=10, debug=True, check=True)

    assert proc.returncode == 0
    assert work.is_dir()
    assert out.parent.is_dir()

    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["cwd"] == str(work.resolve())

    argv = mock_run.call_args.args[0]
    assert str(inp.resolve()) in argv
    assert str(out.resolve()) in argv


def test_run_verbose_adds_kmc_v_without_debug_stream(kmc: KMC, tmp_path: Path) -> None:
    inp, out, work = tmp_path / "in.fa", tmp_path / "db", tmp_path / "w"
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    with patch("ASOkai.Utils._kmc.subprocess.run", return_value=completed) as mock_run:
        kmc.run(inp, out, work, k=10, v=True, debug=False, check=True)

    argv = mock_run.call_args.args[0]
    assert "-v" in argv
    assert mock_run.call_args.kwargs.get("capture_output") is True


def test_run_kmc_failure_raises(kmc: KMC, tmp_path: Path) -> None:
    inp, out, work = tmp_path / "in.fa", tmp_path / "db", tmp_path / "w"
    bad = subprocess.CompletedProcess(args=[], returncode=1, stdout="out", stderr="err")

    with patch("ASOkai.Utils._kmc.subprocess.run", return_value=bad):
        with pytest.raises(KMCExecutionError) as exc_info:
            kmc.run(inp, out, work, check=True, debug=False)

    assert exc_info.value.returncode == 1
    assert exc_info.value.stderr == "err"


def test_run_check_false_returns_failed_process(kmc: KMC, tmp_path: Path) -> None:
    inp, out, work = tmp_path / "in.fa", tmp_path / "db", tmp_path / "w"
    bad = subprocess.CompletedProcess(args=[], returncode=7, stdout="", stderr="")

    with patch("ASOkai.Utils._kmc.subprocess.run", return_value=bad):
        proc = kmc.run(inp, out, work, check=False)
    assert proc.returncode == 7
