#!/usr/bin/env python
"""
Filename: src/ASOkai/_cwl/job_bundle.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Helpers for writing runnable CWL job bundles.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ASOkai._cwl.generation import GeneratedCwlBundle


def _render_readme(label: str, runner_name: str) -> str:
    """Render standalone instructions for one generated job bundle."""
    return f"""# ASOkai CWL Job

This directory contains a prepared ASOkai CWL job bundle for `{label}`.

## Files

- `run.cwl`: generated top-level runtime CWL.
- `publish.cwl`: final tool that publishes every planned output.
- `output-layout.yml`: relative destinations below the chosen output directory.
- `steps/*.cwl`: generated CWL command-line tools for each concrete step run.
- `job.yml`: resolved job inputs from the ASOkai configuration and CLI overrides.
- `README.md`: this file.

## Requirements

ASOkai must be installed on the machine where this job is run, because the
generated step tools call ASOkai command-line entry points. External programs
required by the selected steps must also be available.

## Run Standalone

This job bundle was prepared for `{runner_name}`.

Run the following command from this directory:

```bash
{runner_name} --outdir /path/to/data run.cwl job.yml
```

Inspect `job.yml` before running. File inputs can contain absolute paths from
the machine where the bundle was generated and may need to be updated when the
bundle is moved.

Replace `/path/to/data` with the data directory that should receive the
generated hierarchy. Files at declared output destinations may be replaced;
existing unrelated files below that directory are kept.

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
    job_text = yaml.safe_dump(
        inputs,
        default_flow_style=False,
        sort_keys=False,
    )
    readme_text = _render_readme(label, runner_name)

    parent_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{name_prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    suffix = 1
    while True:
        name = base_name if suffix == 1 else f"{base_name}-{suffix}"
        job_dir = parent_dir / name
        try:
            job_dir.mkdir()
        except FileExistsError:
            suffix += 1
            continue
        break

    try:
        (job_dir / "run.cwl").write_text(bundle.run_cwl, encoding="utf-8")
        (job_dir / "publish.cwl").write_text(
            bundle.publish_cwl,
            encoding="utf-8",
        )
        (job_dir / "output-layout.yml").write_text(
            bundle.output_layout,
            encoding="utf-8",
        )
        steps_dir = job_dir / "steps"
        steps_dir.mkdir()
        for filename, text in bundle.step_cwls.items():
            (steps_dir / filename).write_text(text, encoding="utf-8")
        (job_dir / "job.yml").write_text(job_text, encoding="utf-8")
        (job_dir / "README.md").write_text(
            readme_text,
            encoding="utf-8",
        )
    except BaseException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise

    return job_dir
