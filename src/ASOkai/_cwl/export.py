#!/usr/bin/env python
"""
Filename: src/ASOkai/_cwl/export.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Helpers for writing runnable CWL job bundles.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ASOkai._cwl.generation import GeneratedCwlBundle


def _run_commands(runner_name: str) -> str:
    """Render the standalone command for any CWL runner executable."""
    return f"""```bash
{runner_name} --outdir /path/to/data run.cwl job.yml
```"""


def _readme(label: str, runner_name: str) -> str:
    return f"""# ASOkai CWL Job

This directory contains a prepared ASOkai CWL job bundle for `{label}`.

## Files

- `run.cwl`: generated top-level runtime CWL.
- `publish.cwl`: final tool that publishes every planned output.
- `output-layout.yml`: relative destinations below the chosen output directory.
- `steps/*.cwl`: generated CWL command-line tools for each ASOkai step.
- `job.yml`: resolved job inputs from the ASOkai configuration and CLI overrides.
- `README.md`: this file.

## Requirements

ASOkai must be installed on the machine where this job is run, because the
generated step tools call ASOkai command-line entry points.

## Run Standalone

This job bundle was prepared for `{runner_name}`.

{_run_commands(runner_name)}

Replace `/path/to/data` with the data directory that should receive the
generated hierarchy. Existing unrelated files below that directory are kept.

`run.cwl` can also be used as a subworkflow. Its declared inputs and outputs
are the interface that a parent CWL workflow must wire.
"""


def write_cwl_job_bundle(
    *,
    bundle: GeneratedCwlBundle,
    inputs: dict[str, Any],
    parent_dir: Path,
    label: str,
    runner_name: str,
    name_prefix: str,
) -> Path:
    """Write a timestamped CWL job bundle under *parent_dir*."""
    base_name = f"{name_prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    job_dir = parent_dir / base_name
    suffix = 2
    while job_dir.exists():
        job_dir = parent_dir / f"{base_name}-{suffix}"
        suffix += 1
    job_dir.mkdir(parents=True, exist_ok=False)

    (job_dir / "run.cwl").write_text(bundle.run_cwl, encoding="utf-8")
    (job_dir / "publish.cwl").write_text(bundle.publish_cwl, encoding="utf-8")
    (job_dir / "output-layout.yml").write_text(
        bundle.output_layout,
        encoding="utf-8",
    )
    steps_dir = job_dir / "steps"
    steps_dir.mkdir(parents=True, exist_ok=True)
    for filename, text in bundle.step_cwls.items():
        (steps_dir / filename).write_text(text, encoding="utf-8")
    (job_dir / "job.yml").write_text(
        yaml.safe_dump(inputs, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    (job_dir / "README.md").write_text(
        _readme(label, runner_name),
        encoding="utf-8",
    )

    return job_dir
