"""
Filename: src/ASOkai/pipeline/runner.py
Description: Resolves dependencies, maps config to CWL inputs, and invokes Toil.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path

from pipeline import config as cfg
from pipeline.base import Step
from pipeline.registry import get_steps, get_tasks, get_workflows

logger = logging.getLogger(__name__)


def _resolve_inputs(step: Step, config: dict) -> dict:
    """Map CWL input names to values using the step's config_map.

    Missing keys are silently omitted so optional CWL inputs (string?) that
    are not present in the config are not passed at all.
    """
    inputs = {}
    for cwl_input, config_key in step.config_map.items():
        try:
            value = cfg.resolve(config, config_key)
            inputs[cwl_input] = value
        except KeyError:
            pass
    
    steps = get_steps()
    for dep_name in step.dependencies:
        dep_step = steps.get(dep_name)
        if dep_step is None:
            continue
        for output_key, path in dep_step.output_paths(config).items():
            inputs[output_key] = {"class": "File", "path": str(path.resolve())}
    
    return inputs


def _toil_run(cwl_path: str, inputs: dict, outdir: Path) -> None:
    """Invoke toil-cwl-runner as a subprocess."""
    outdir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(inputs, f)
        inputs_file = f.name

    cmd = [
        "toil-cwl-runner",
        "--outdir", str(outdir),
        # "--realTimeLogging", "true",
        cwl_path,
        inputs_file,
    ]
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"toil-cwl-runner failed for {cwl_path} (exit {result.returncode})")


def run_step(
    step_name: str,
    config: dict,
    *,
    force: bool = False,
    dry_run: bool = False,
    recursive: bool = False,
) -> dict[str, Path] | None:
    """
    Run a single step by name.

    Dependencies are checked first:
    - If their outputs already exist, proceed regardless.
    - If their outputs are missing and recursive=True, run them automatically.
    - If their outputs are missing and recursive=False, raise an error.
    """
    steps = get_steps()
    if step_name not in steps:
        raise ValueError(f"Unknown step '{step_name}'. Run 'ASOkai list steps' to see available steps.")

    step = steps[step_name]
    if not isinstance(step, Step):
        raise TypeError(f"Step '{step_name}' does not conform to the Step protocol.")

    for dep in step.dependencies:
        dep_step = steps.get(dep)
        if dep_step is None:
            raise ValueError(f"Step '{step_name}' depends on unknown step '{dep}'.")
        if not isinstance(dep_step, Step):
            raise TypeError(f"Dependency '{dep}' does not conform to the Step protocol.")
        if dep_step.outputs_exist(config):
            logger.debug("[%s] dependency '%s' already satisfied.", step.name, dep)
        elif recursive:
            logger.info("[%s] dependency '%s' missing, running it.", step.name, dep)
            run_step(dep, config, force=force, dry_run=dry_run, recursive=recursive)
        else:
            raise RuntimeError(
                f"Step '{step_name}' requires '{dep}' but its outputs are missing. "
                f"Run '{dep}' first, or use --recursive to run dependencies automatically."
            )

    # skip if outputs already exist
    if not force and step.outputs_exist(config):
        outputs = step.output_paths(config)
        logger.info("[%s] outputs exist, skipping.", step.name)
        for name, path in outputs.items():
            logger.info("  %s: %s", name, path)
        return outputs

    if force and not dry_run:
        logger.info("[%s] force=True, cleaning up existing outputs.", step.name)
        step.cleanup(config)

    inputs = _resolve_inputs(step, config)
    outdir = step.outdir(config)

    if dry_run:
        logger.info("[%s] dry-run — would invoke toil-cwl-runner:", step.name)
        logger.info("  CWL : %s", step.cwl_path)
        logger.info("  Inputs: %s", inputs)
        outputs = step.output_paths(config)
        logger.info("  Outputs:")
        for name, path in outputs.items():
            logger.info("    %s: %s", name, path)
        return outputs

    logger.info("[%s] running.", step.name)
    _toil_run(step.cwl_path, inputs, outdir)
    return step.output_paths(config)


def run_task(
    task_name: str,
    config: dict,
    *,
    force: bool = False,
    dry_run: bool = False,
    recursive: bool = False,
) -> dict[str, Path] | None:
    tasks = get_tasks()
    if task_name not in tasks:
        raise ValueError(f"Unknown task '{task_name}'. Run 'ASOkai list tasks' to see available tasks.")
    task = tasks[task_name]

    for dep in task.dependencies:
        dep_task = tasks.get(dep)
        if dep_task is None:
            raise ValueError(f"Task '{task_name}' depends on unknown task '{dep}'.")
        if not (hasattr(dep_task, "outputs_exist") and dep_task.outputs_exist(config)):
            if recursive:
                logger.info("[%s] dependency '%s' missing, running it.", task.name, dep)
                run_task(dep, config, force=force, dry_run=dry_run, recursive=recursive)
            else:
                raise RuntimeError(
                    f"Task '{task_name}' requires '{dep}' but its outputs are missing. "
                    f"Run '{dep}' first, or use --recursive to run dependencies automatically."
                )

    inputs = _resolve_inputs(task, config)
    outdir = task.outdir(config) if hasattr(task, "outdir") else Path(config["datadir"]).resolve()
    if dry_run:
        logger.info("[%s] dry-run — would invoke toil-cwl-runner:", task.name)
        logger.info("  CWL : %s", task.cwl_path)
        logger.info("  Inputs: %s", inputs)
        return None
    _toil_run(task.cwl_path, inputs, outdir)
    return None


def run_workflow(
    workflow_name: str,
    config: dict,
    *,
    force: bool = False,
    dry_run: bool = False,
    recursive: bool = False,
) -> None:
    workflows = get_workflows()
    if workflow_name not in workflows:
        raise ValueError(f"Unknown workflow '{workflow_name}'. Run 'ASOkai list workflows' to see available workflows.")
    workflow = workflows[workflow_name]
    inputs = _resolve_inputs(workflow, config)
    outdir = Path(config["datadir"]).resolve()
    if dry_run:
        logger.info("[%s] dry-run — would invoke toil-cwl-runner:", workflow.name)
        logger.info("  CWL : %s", workflow.cwl_path)
        logger.info("  Inputs: %s", inputs)
        return
    _toil_run(workflow.cwl_path, inputs, outdir)
