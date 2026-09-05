#!/usr/bin/env python
"""
Filename: tests/integration/test_kmc_kff.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Real-binary integration coverage for KMC KFF indexes.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from ASOkai.Utils import KMC, KMCTools
from ASOkai._pipeline.contracts.file_types import KffFile


@pytest.mark.integration
@pytest.mark.skipif(
    shutil.which("kmc") is None or shutil.which("kmc_tools") is None,
    reason="kmc and kmc_tools are required",
)
def test_kmc_writes_a_single_readable_kff_file(tmp_path: Path) -> None:
    fasta = tmp_path / "genome.fa"
    fasta.write_text(">sequence\nACGTACGTACGTACGT\n", encoding="utf-8")
    output = tmp_path / "genome.kff"

    KMC().run(
        fasta,
        output,
        tmp_path / "scratch",
        k=5,
        m=2,
        f="fa",
        ci=1,
        o="kff",
        hp=True,
        debug=False,
    )

    KffFile().validate(output)
    assert not output.with_suffix(".kff.kff").exists()

    dumped = tmp_path / "counts.txt"
    KMCTools.Transform().dump(dumped).run(output, debug=False)
    assert dumped.read_text(encoding="utf-8").strip()
