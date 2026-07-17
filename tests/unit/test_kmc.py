#!/usr/bin/env python
"""Tests for ASOkai.Utils.kmc (KMC, KMCDatabase, KMCExecutionError)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from ASOkai.Utils import KMC, KMCDatabase
from ASOkai.Utils import KMCExecutionError


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
        kmc.run(inp, out, work, m=0)
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


def test_kmcdatabase_paths(tmp_path: Path) -> None:
    prefix = tmp_path / "mydb"
    db = KMCDatabase(prefix, k=15)

    assert db.pre_path == Path(f"{prefix.resolve()}.kmc_pre")
    assert db.suf_path == Path(f"{prefix.resolve()}.kmc_suf")
    assert db.exists is False

    db.pre_path.write_text("x")
    db.suf_path.write_text("y")
    assert db.exists is True


def test_resolve_prefix_defaults(tmp_path: Path) -> None:
    inp = tmp_path / "reads.fa"
    p = KMCDatabase.resolve_prefix(inp)
    assert p.name == "reads.k25.ci2.cs255.cx1e9"
    assert p.parent == inp.parent.resolve()


def test_resolve_prefix_custom_dir(tmp_path: Path) -> None:
    inp = tmp_path / "sub" / "reads.fq"
    alt = tmp_path / "outdir"
    p = KMCDatabase.resolve_prefix(inp, output_dir=alt, k=21, ci=1)

    assert p.parent == alt.resolve()
    assert p.name == "reads.k21.ci1.cs255.cx1e9"


def test_build_without_output_returns_none_when_no_shards(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "in.fa"
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    with patch.object(kmc, "run", return_value=completed):
        result = KMCDatabase.build(inp, kmc, w=True)
    assert result is None


def test_build_without_output_returns_existing_handle(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "in.fa"
    prefix = KMCDatabase.resolve_prefix(inp)
    Path(f"{prefix}.kmc_pre").write_text("p")
    Path(f"{prefix}.kmc_suf").write_text("s")

    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch.object(kmc, "run", return_value=completed):
        db = KMCDatabase.build(inp, kmc, w=True)

    assert isinstance(db, KMCDatabase)
    assert db.exists


def test_build_success_returns_handle(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "in.fa"
    expected_prefix = KMCDatabase.resolve_prefix(inp, k=12)
    scratch_seen: list[Path] = []

    def fake_run(ip: Path, op: Path, wd: Path, **kwargs: object) -> subprocess.CompletedProcess[str]:
        scratch_seen.append(Path(wd))
        assert Path(wd).is_dir()

        p = Path(op).resolve()
        assert p == expected_prefix.resolve()

        Path(f"{p}.kmc_pre").write_text("p")
        Path(f"{p}.kmc_suf").write_text("s")
        return subprocess.CompletedProcess(args=["kmc"], returncode=0, stdout="", stderr="")

    with patch.object(kmc, "run", side_effect=fake_run):
        db = KMCDatabase.build(inp, kmc, k=12)

    assert not scratch_seen[0].exists()
    assert isinstance(db, KMCDatabase)
    assert db.k == 12
    assert db.exists


def test_build_missing_files_after_success_raises(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "in.fa"
    completed = subprocess.CompletedProcess(args=["kmc"], returncode=0, stdout="", stderr="")

    with patch.object(kmc, "run", return_value=completed):
        with pytest.raises(KMCExecutionError, match="missing"):
            KMCDatabase.build(inp, kmc, k=12)


def test_build_keeps_explicit_working_directory(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "in.fa"
    work = tmp_path / "persist_scratch"
    work.mkdir()
    completed = subprocess.CompletedProcess(args=["kmc"], returncode=0, stdout="", stderr="")

    def fake_run(
        ip: str | Path,
        op: str | Path,
        wd: str | Path,
        **kw: object,
    ) -> subprocess.CompletedProcess[str]:
        assert Path(wd).resolve() == work.resolve()
        p = Path(str(op)).resolve()
        Path(f"{p}.kmc_pre").write_text("p")
        Path(f"{p}.kmc_suf").write_text("s")
        return completed

    with patch.object(kmc, "run", side_effect=fake_run):
        db = KMCDatabase.build(inp, kmc, working_dir=work, k=12)

    assert db is not None
    assert work.is_dir()


def test_build_skips_when_exists(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "s.fa"
    prefix = KMCDatabase.resolve_prefix(inp, k=25)
    Path(f"{prefix}.kmc_pre").write_text("p")
    Path(f"{prefix}.kmc_suf").write_text("s")

    with patch.object(kmc, "run") as mock_run:
        db = KMCDatabase.build(inp, kmc)

    mock_run.assert_not_called()
    assert db is not None
    assert db.exists


def test_build_force_rebuilds(kmc: KMC, tmp_path: Path) -> None:
    inp = tmp_path / "s.fa"
    prefix = KMCDatabase.resolve_prefix(inp, k=25)
    Path(f"{prefix}.kmc_pre").write_text("p")
    Path(f"{prefix}.kmc_suf").write_text("s")

    completed = subprocess.CompletedProcess(args=["kmc"], returncode=0, stdout="", stderr="")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(f"{prefix}.kmc_pre").write_text("p2")
        Path(f"{prefix}.kmc_suf").write_text("s2")
        return completed

    with patch.object(kmc, "run", side_effect=fake_run):
        KMCDatabase.build(inp, kmc, force=True)

    assert Path(f"{prefix}.kmc_pre").read_text() == "p2"
