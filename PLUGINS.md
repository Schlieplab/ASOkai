# Plugin Architecture for ASOkai

ASOkai supports external plugins to add custom steps, tasks, and workflows without modifying the core codebase. Plugins are discovered and loaded automatically via Python entry points.

## How Plugins Work

The registry (`ASOkai.pipeline.registry`) loads plugins at runtime using `importlib.metadata.entry_points`. Your external package just needs to:

1. Implement a class that follows the `Step` protocol (defined in `ASOkai.pipeline.base`)
2. Declare an entry point in your `pyproject.toml`

ASOkai will automatically discover and instantiate your plugin when the CLI runs.

## Creating a Plugin Step

### Step 1: Implement the `Step` Protocol

Create a file in your external package, e.g. `my_plugin/steps/my_step.py`:

```python
"""my_plugin/steps/my_step.py"""
from pathlib import Path
from importlib.resources import files

class MyCustomStep:
    name = "my-custom-step"
    description = "Does something custom."
    dependencies: list[str] = ["some-other-step"]
    config_map = {
        "input1": "config.key1",
        "input2": "config.key2",
    }

    @property
    def cwl_path(self) -> str:
        return str(files("my_plugin.cwl.steps").joinpath("my-custom-step.cwl"))

    def outdir(self, config: dict) -> Path:
        return Path(config["datadir"]) / "custom" / config.get("target_id", "default")

    def output_paths(self, config: dict) -> dict[str, Path]:
        base = self.outdir(config)
        return {
            "output1": base / "result.json",
        }

    def outputs_exist(self, config: dict) -> bool:
        return all(p.exists() for p in self.output_paths(config).values())

    def cleanup(self, config: dict) -> None:
        for p in self.output_paths(config).values():
            if p.exists():
                p.unlink()
```

### Step 2: Implement the CLI Entrypoint

In the same file (or a separate one), add a `main()` function:

```python
import argparse
import sys

def main() -> int:
    """Called by CWL baseCommand."""
    parser = argparse.ArgumentParser(description="My custom step.")
    parser.add_argument("--input1", required=True, help="First input.")
    parser.add_argument("--input2", required=True, help="Second input.")
    parser.add_argument("--outdir", required=True, type=Path, help="Output directory.")

    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    # Your logic here
    result = process_inputs(args.input1, args.input2)

    output_path = args.outdir / "result.json"
    with open(output_path, 'w') as f:
        json.dump(result, f)

    print(f"output1\t{output_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

### Step 3: Create the CWL Tool Definition

Create `my_plugin/cwl/steps/my-custom-step.cwl`:

```yaml
#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool

baseCommand: my-custom-step

inputs:
  input1:
    type: string
    inputBinding:
      prefix: --input1

  input2:
    type: string
    inputBinding:
      prefix: --input2

outputs:
  output1:
    type: File
    outputBinding:
      glob: "result.json"
```

### Step 4: Declare Entry Points in `pyproject.toml`

In your plugin package's `pyproject.toml`, declare the entry point:

```toml
[project.entry-points."asokai.steps"]
my-custom-step = "my_plugin.steps.my_step:MyCustomStep"

[project.scripts]
my-custom-step = "my_plugin.steps.my_step:main"

[tool.setuptools.package-data]
"my_plugin.cwl.steps" = ["*.cwl"]
```

### Step 5: Install

Install your plugin in development mode:

```bash
pip install -e /path/to/my_plugin
```

### Step 6: Use It

The step is now discoverable:

```bash
ASOkai list steps
ASOkai describe my-custom-step
ASOkai run my-custom-step --config config.yaml
```

## For Tasks and Workflows

Tasks and workflows do **not** ship static CWL files. ASOkai generates workflow CWL at runtime from your step definitions.

- **`PipelineUnit`** (`pipeline.base.PipelineUnit`): shared base protocol — `name`, `description`, `outdir`, `output_paths`, `outputs_exist`, `cleanup`. `Step`, `Task`, and `Workflow` all extend it.
- **Task** (`pipeline.base.Task`): `steps` — ordered list of **step** names only.
- **Workflow** (`pipeline.base.Workflow`): `units` — ordered `("step", name)`, `("task", name)`, or `("workflow", name)` pairs (nested workflows allowed).

The process is the same—use entry points `asokai.tasks` and `asokai.workflows` respectively:

```toml
[project.entry-points."asokai.tasks"]
my-task = "my_plugin.tasks.my_task:MyCustomTask"

[project.entry-points."asokai.workflows"]
my-workflow = "my_plugin.workflows.my_workflow:MyCustomWorkflow"
```

## Key Points

- **Protocol-based:** Everything implements `PipelineUnit` at minimum. Steps add `dependencies`, `config_map`, and `cwl_path`. Tasks add `steps`. Workflows add `units` (see above).
- **Entry points:** Declare in your `pyproject.toml` under `asokai.steps`, `asokai.tasks`, or `asokai.workflows`.
- **CLI entrypoint:** Register a `[project.scripts]` entry for `baseCommand` to work.
- **CWL files:** Use `importlib.resources.files()` to robustly locate your CWL files.
- **No config parsing:** The CLI handles config loading and passing—your step receives resolved inputs via CLI arguments.

## Example Plugin Structure

```
my_plugin/
├── pyproject.toml
├── my_plugin/
│   ├── __init__.py
│   ├── steps/
│   │   ├── __init__.py
│   │   └── my_step.py
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── my_task.py
│   └── cwl/
│       ├── __init__.py
│       ├── steps/
│       │   ├── __init__.py
│       │   └── my-step.cwl
│       └── tasks/
│           ├── __init__.py
│           └── my-task.cwl
└── tests/
    └── test_my_step.py
```
