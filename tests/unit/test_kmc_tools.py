#!/usr/bin/env python
"""
Filename: tests/unit/test_kmc_tools.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Tests for ASOkai.Utils.KMCTools (Simple, Transform, Filter, Complex).
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from ASOkai.Utils import KMCTools
from ASOkai.Utils.KMCTools import KMCToolsExecutionError


@pytest.fixture
def fake_kmc_tools(tmp_path: Path) -> Path:
    exe = tmp_path / "kmc_tools"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    return exe


@pytest.fixture
def tools_exe(fake_kmc_tools: Path) -> str:
    return str(fake_kmc_tools)


def test_kmc_tools_namespace_supports_both_public_import_styles() -> None:
    assert KMCTools.__name__ == "ASOkai.Utils.KMCTools"
    assert KMCTools.KMCToolsExecutionError is KMCToolsExecutionError


def test_resolve_executable_missing() -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        KMCTools.Simple("___not_a_real_kmc_tools_binary___")


def test_transform_minimal_chain(tools_exe: str, tmp_path: Path) -> None:
    db = tmp_path / "db"
    out_r = tmp_path / "reduced"
    out_h = tmp_path / "histo.txt"
    out_d = tmp_path / "dump.txt"

    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils.KMCTools._base.subprocess.run", return_value=completed) as mock_run:
        KMCTools.Transform(tools_exe).reduce(out_r, cx=10).histogram(out_h).dump(out_d).run(db, t=8)

    argv = mock_run.call_args.args[0]
    assert argv[0] == tools_exe
    assert argv[1:3] == ["-t8", "transform"]
    assert argv[3] == str(db.resolve())
    assert argv[4:7] == ["reduce", str(out_r.resolve()), "-cx10"]
    assert argv[7:9] == ["histogram", str(out_h.resolve())]
    assert argv[9:11] == ["dump", str(out_d.resolve())]


def test_transform_run_input_ci_cx(tools_exe: str, tmp_path: Path) -> None:
    db = tmp_path / "kdb"
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils.KMCTools._base.subprocess.run", return_value=completed) as mock_run:
        KMCTools.Transform(tools_exe).sort().run(db, ci=3, cx=100, v=True, hp=True)

    argv = mock_run.call_args.args[0]
    assert "-v" in argv
    assert "-hp" in argv
    assert argv[argv.index("transform") + 1] == str(db.resolve())
    assert "-ci3" in argv
    assert "-cx100" in argv
    idx = argv.index("transform")
    assert argv[idx + 1 : idx + 4] == [str(db.resolve()), "-ci3", "-cx100"]


def test_transform_sort_without_output_path(tools_exe: str, tmp_path: Path) -> None:
    db = tmp_path / "kdb"
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils.KMCTools._base.subprocess.run", return_value=completed) as mock_run:
        KMCTools.Transform(tools_exe).sort(ci=5).run(db)

    argv = mock_run.call_args.args[0]
    tail = argv[argv.index("transform") + 1 :]
    assert tail == [str(db.resolve()), "sort", "-ci5"]


def test_transform_compact_dump_set_counts(tools_exe: str, tmp_path: Path) -> None:
    db = tmp_path / "kdb"
    comp_out = tmp_path / "c.kmc"
    dump_out = tmp_path / "d.txt"
    sc_out = tmp_path / "sc.kmc"

    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils.KMCTools._base.subprocess.run", return_value=completed) as mock_run:
        (
            KMCTools.Transform(tools_exe)
            .compact(comp_out, o="kff")
            .dump(dump_out, s=True)
            .set_counts(42, sc_out, o="kmc")
            .run(db)
        )

    argv = mock_run.call_args.args[0]
    ops = argv[argv.index("transform") + 1 :]
    assert ops[0] == str(db.resolve())
    i = 1
    assert ops[i : i + 3] == ["compact", str(comp_out.resolve()), "-okff"]
    i += 3
    assert ops[i : i + 3] == ["dump", "-s", str(dump_out.resolve())]
    i += 3
    assert ops[i : i + 4] == ["set_counts", "42", str(sc_out.resolve()), "-okmc"]


def test_simple_chained_union_intersect(tools_exe: str, tmp_path: Path) -> None:
    km1, km2 = tmp_path / "kmers1", tmp_path / "kmers2"
    u = tmp_path / "union_out"
    ix = tmp_path / "inter_out"

    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils.KMCTools._base.subprocess.run", return_value=completed) as mock_run:
        (
            KMCTools.Simple(tools_exe)
            .union(u, cs=65536, oc="left", o="kff")
            .intersect(ix, oc="max")
            .run(km1, km2, input1_ci=3, input1_cx=70000)
        )

    argv = mock_run.call_args.args[0]
    assert argv[0] == tools_exe
    i = argv.index("simple")
    assert argv[i + 1] == str(km1.resolve())
    assert "-ci3" in argv and "-cx70000" in argv
    assert argv[i + 1 + 1 + 2] == str(km2.resolve())  # km1, -ci3, -cx70000, km2
    km2_idx = argv.index(str(km2.resolve()))
    rest = argv[km2_idx + 1 :]
    assert rest[0] == "union"
    assert rest[1] == str(u.resolve())
    assert "-cs65536" in rest
    assert "-okff" in rest
    assert "-ocleft" in rest
    ix_pos = rest.index("intersect")
    assert rest[ix_pos + 1] == str(ix.resolve())
    assert "-ocmax" in rest[ix_pos:]


@pytest.mark.parametrize(
    "method,op_name",
    [
        ("intersect", "intersect"),
        ("union", "union"),
        ("kmers_subtract", "kmers_subtract"),
        ("counters_subtract", "counters_subtract"),
        ("reverse_kmers_subtract", "reverse_kmers_subtract"),
        ("reverse_counters_subtract", "reverse_counters_subtract"),
    ],
)
def test_simple_each_operation_emits_name(
    tools_exe: str, tmp_path: Path, method: str, op_name: str
) -> None:
    a, b, o = tmp_path / "a", tmp_path / "b", tmp_path / "out"
    s = KMCTools.Simple(tools_exe)
    getattr(s, method)(o)

    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils.KMCTools._base.subprocess.run", return_value=completed) as mock_run:
        s.run(a, b)

    argv = mock_run.call_args.args[0]
    assert op_name in argv
    assert argv[argv.index(op_name) + 1] == str(o.resolve())


def test_simple_input2_ci_cx(tools_exe: str, tmp_path: Path) -> None:
    a, b, o = tmp_path / "a", tmp_path / "b", tmp_path / "o"
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils.KMCTools._base.subprocess.run", return_value=completed) as mock_run:
        KMCTools.Simple(tools_exe).intersect(o).run(a, b, input2_ci=10, input2_cx=99)

    argv = mock_run.call_args.args[0]
    a_idx = argv.index(str(a.resolve()))
    b_idx = argv.index(str(b.resolve()))
    assert argv[b_idx + 1 : b_idx + 3] == ["-ci10", "-cx99"]
    assert b_idx > a_idx


def test_filter_flags_and_paths(tools_exe: str, tmp_path: Path) -> None:
    db, inp, outp = tmp_path / "kmc_db", tmp_path / "in.fq", tmp_path / "out.fq"

    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils.KMCTools._base.subprocess.run", return_value=completed) as mock_run:
        KMCTools.Filter(tools_exe).run(
            db,
            inp,
            outp,
            trim=True,
            hm=True,
            db_ci=3,
            read_ci=0.5,
            read_cx=1.0,
            read_f="q",
            output_f="a",
            t=4,
        )

    argv = mock_run.call_args.args[0]
    assert argv[0] == tools_exe
    assert argv[1:3] == ["-t4", "filter"]
    assert "-t" in argv
    assert "-hm" in argv
    f_idx = argv.index("filter")
    assert argv[f_idx + 1] == "-t"  # trim flag immediately after subcommand
    assert argv[f_idx + 2] == "-hm"
    assert str(db.resolve()) in argv
    assert "-ci3" in argv
    assert str(inp.resolve()) in argv
    assert "-ci0.5" in argv and "-cx1.0" in argv
    assert "-fq" in argv
    assert str(outp.resolve()) in argv
    assert "-fa" in argv


def test_filter_no_trim_global_t_only(tools_exe: str, tmp_path: Path) -> None:
    db, inp, outp = tmp_path / "db", tmp_path / "i.fq", tmp_path / "o.fq"
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils.KMCTools._base.subprocess.run", return_value=completed) as mock_run:
        KMCTools.Filter(tools_exe).run(db, inp, outp, t=8)

    argv = mock_run.call_args.args[0]
    assert argv[0:3] == [tools_exe, "-t8", "filter"]
    assert "-t" not in argv  # trim off: no bare filter -t (only global -t8)


def test_complex(tools_exe: str, tmp_path: Path) -> None:
    ops_file = tmp_path / "ops.txt"
    ops_file.write_text("INPUT:\nset1 = a\nOUTPUT:\nout = set1\n")

    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils.KMCTools._base.subprocess.run", return_value=completed) as mock_run:
        KMCTools.Complex(tools_exe).run(ops_file, t=2, v=True)

    argv = mock_run.call_args.args[0]
    assert argv[:4] == [tools_exe, "-t2", "-v", "complex"]
    assert argv[4] == str(ops_file.resolve())


def test_run_failure_raises(tools_exe: str, tmp_path: Path) -> None:
    db = tmp_path / "db"
    bad = subprocess.CompletedProcess(args=[], returncode=2, stdout="o", stderr="e")

    with patch("ASOkai.Utils.KMCTools._base.subprocess.run", return_value=bad):
        with pytest.raises(KMCTools.KMCToolsExecutionError) as exc_info:
            KMCTools.Transform(tools_exe).sort().run(db, check=True, debug=False)

    assert exc_info.value.returncode == 2
    assert exc_info.value.stderr == "e"
    assert exc_info.value.cmd[0] == tools_exe


def test_run_check_false_returns_failed_process(tools_exe: str, tmp_path: Path) -> None:
    db = tmp_path / "db"
    bad = subprocess.CompletedProcess(args=[], returncode=5, stdout="", stderr="")

    with patch("ASOkai.Utils.KMCTools._base.subprocess.run", return_value=bad):
        proc = KMCTools.Transform(tools_exe).sort().run(db, check=False)

    assert proc.returncode == 5


def test_run_passes_cwd(tools_exe: str, tmp_path: Path) -> None:
    db = tmp_path / "db"
    work = tmp_path / "subdir"
    work.mkdir()

    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ASOkai.Utils.KMCTools._base.subprocess.run", return_value=completed) as mock_run:
        KMCTools.Transform(tools_exe).sort().run(db, cwd=work)

    assert mock_run.call_args.kwargs["cwd"] == str(work.resolve())


def test_debug_false_captures_output(tools_exe: str, tmp_path: Path) -> None:
    db = tmp_path / "db"
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    with patch("ASOkai.Utils.KMCTools._base.subprocess.run", return_value=completed) as mock_run:
        KMCTools.Transform(tools_exe).sort().run(db, debug=False)

    assert mock_run.call_args.kwargs.get("capture_output") is True


def test_same_instance_can_run_twice(tools_exe: str, tmp_path: Path) -> None:
    db1, db2 = tmp_path / "d1", tmp_path / "d2"
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    tf = KMCTools.Transform(tools_exe)
    with patch("ASOkai.Utils.KMCTools._base.subprocess.run", return_value=completed) as mock_run:
        tf.sort().run(db1)
        first_cmd = mock_run.call_args.args[0][:]
        tf.reduce(tmp_path / "o").run(db2)
        second_cmd = mock_run.call_args.args[0][:]

    assert "d1" in first_cmd[first_cmd.index("transform") + 1]
    assert "reduce" in second_cmd
    assert second_cmd[second_cmd.index("transform") + 1] == str(db2.resolve())
