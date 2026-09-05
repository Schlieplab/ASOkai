#!/usr/bin/env python
"""
Filename: tests/integration/test_pipeline_execution.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: End-to-end coverage for planning, CWL execution, and publication.
License: LGPL-3.0-or-later
"""

import os
from pathlib import Path
import shutil

import pytest

from ASOkai._cwl.executors import CwlToolExecutor, ToilExecutor
from ASOkai._pipeline.runner import run_all
from ASOkai._pipeline.steps.core.build_genome_kmer_index import (
    BuildGenomeKmerIndexStep,
)


def _install_fake_kmc_toolchain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Put deterministic KMC-compatible executables first on PATH."""
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    kmc = bin_directory / "kmc"
    kmc.write_text(
        "#!/usr/bin/env python\n"
        "from pathlib import Path\n"
        "import sys\n"
        "Path(sys.argv[-2] + '.kff').write_bytes(b'KFF\\x01index-dataKFF')\n",
        encoding="utf-8",
    )
    kmc.chmod(0o755)
    kmc_tools = bin_directory / "kmc_tools"
    kmc_tools.write_text(
        "#!/usr/bin/env python\n"
        "from pathlib import Path\n"
        "import sys\n"
        "transform = sys.argv.index('transform')\n"
        "source = Path(sys.argv[transform + 1])\n"
        "content = source.read_bytes()\n"
        "if not content.startswith(b'KFF') or not content.endswith(b'KFF'):\n"
        "    raise SystemExit(2)\n"
        "dump = sys.argv.index('dump')\n"
        "Path(sys.argv[dump + 1]).write_text('ACGT\\t1\\n')\n",
        encoding="utf-8",
    )
    kmc_tools.chmod(0o755)
    monkeypatch.setenv(
        "PATH",
        f"{bin_directory}{os.pathsep}{os.environ.get('PATH', '')}",
    )


@pytest.mark.integration
@pytest.mark.skipif(
    shutil.which("ASOkai") is None,
    reason="the ASOkai executable is required",
)
@pytest.mark.parametrize(
    "executor",
    [
        pytest.param(
            CwlToolExecutor(extra_args=["--no-container"]),
            marks=pytest.mark.skipif(
                shutil.which("cwltool") is None,
                reason="cwltool is required",
            ),
            id="cwltool",
        ),
        pytest.param(
            ToilExecutor(
                extra_args=["--no-container", "--clean", "always"],
                capture_worker_output=True,
            ),
            marks=pytest.mark.skipif(
                shutil.which("toil-cwl-runner") is None,
                reason="toil-cwl-runner is required",
            ),
            id="toil",
        ),
    ],
)
def test_registered_step_executes_validates_and_publishes_output(
    tmp_path,
    monkeypatch,
    executor,
):
    _install_fake_kmc_toolchain(tmp_path, monkeypatch)
    dna = tmp_path / "input.fa"
    dna.write_text(">chr1\nACGTACGT\n", encoding="utf-8")
    config = {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "GRCh38",
            "ensembl_release": 114,
            "source": "ensembl",
            "species": "Homo_sapiens",
        },
        "target": {
            "target_id": "ENSG1",
            "k": 16,
            "region": "pre-mrna",
        },
        "steps": {
            "build-genome-kmer-index": {
                "inputs": {
                    "dna": {"path_override": str(dna)},
                },
            },
        },
        "resources": {
            "default": {
                "n_processes": 1,
                "memory_mb": 4096,
            },
        },
    }

    outputs = run_all(
        [BuildGenomeKmerIndexStep()],
        config,
        force=True,
        executor=executor,
    )

    output = (
        tmp_path
        / "GRCh38"
        / "ensembl"
        / "114"
        / "genome"
        / "indexes"
        / "kmc"
        / "GRCh38.k16.kff"
    )
    assert outputs == {
        "build-genome-kmer-index.kmer_index": output,
    }
    assert output.read_bytes() == b"KFF\x01index-dataKFF"
    assert len(list((tmp_path / ".asokai" / "validation").glob("*.json"))) == 1

    job_dirs = list((tmp_path / "jobs").glob("asokai-job-*"))
    assert len(job_dirs) == 1
    step_cwl = job_dirs[0] / "steps" / "build-genome-kmer-index.cwl"
    assert "baseCommand:\n- ASOkai\n- step" in step_cwl.read_text(encoding="utf-8")
