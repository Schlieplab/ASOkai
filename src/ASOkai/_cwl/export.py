"""
Helpers for writing runnable CWL job bundles.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def _run_commands(job_dir: Path, runner_name: str) -> str:
    cd_line = f"cd {job_dir.resolve()}"
    if runner_name == "toil-cwl-runner":
        primary = f"{cd_line}\ntoil-cwl-runner --outdir out workflow.cwl job.yml"
        alternate = f"{cd_line}\ncwltool workflow.cwl job.yml"
    else:
        primary = f"{cd_line}\ncwltool workflow.cwl job.yml"
        alternate = f"{cd_line}\ntoil-cwl-runner --outdir out workflow.cwl job.yml"
    return f"""Selected runner:

```bash
{primary}
```

Alternative runner:

```bash
{alternate}
```"""


def _readme(label: str, job_dir: Path, runner_name: str) -> str:
    return f"""# ASOkai CWL Job

This directory contains a prepared ASOkai CWL job bundle for `{label}`.

## Files

- `workflow.cwl`: generated CWL workflow.
- `job.yml`: resolved job inputs from the ASOkai configuration and CLI overrides.
- `README.md`: this file.

## Requirements

ASOkai must be installed on the machine where this workflow is run, because the
workflow steps call ASOkai command-line entry points.

## Run Standalone

This job bundle was prepared for `{runner_name}`.

{_run_commands(job_dir, runner_name)}

## Use As A Subworkflow

```yaml
cwlVersion: v1.2
class: Workflow

inputs:
  job_inputs: Any

steps:
  asokai:
    run: workflow.cwl
    in: []
    out: []

outputs: {{}}
```

Wire the parent workflow inputs to `workflow.cwl` inputs as needed. The bundled
`job.yml` shows the concrete values ASOkai resolved for this job.
"""


def write_cwl_job_bundle(
    *,
    cwl_doc: str,
    inputs: dict[str, Any],
    parent_dir: Path,
    label: str,
    runner_name: str,
    name_prefix: str = "asokai-job",
) -> Path:
    """Write a timestamped CWL job bundle under *parent_dir*."""
    base_name = f"{name_prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    job_dir = parent_dir / base_name
    suffix = 2
    while job_dir.exists():
        job_dir = parent_dir / f"{base_name}-{suffix}"
        suffix += 1
    job_dir.mkdir(parents=True, exist_ok=False)

    (job_dir / "workflow.cwl").write_text(cwl_doc)
    (job_dir / "job.yml").write_text(
        yaml.safe_dump(inputs, default_flow_style=False, sort_keys=False)
    )
    (job_dir / "README.md").write_text(_readme(label, job_dir, runner_name))

    return job_dir
