# ASOkai plugins

An ASOkai plugin is an independently installed Python package that contributes
steps, tasks, workflows, or configuration schemas. ASOkai discovers these
components through Python entry points; a plugin does not modify the ASOkai
source tree or maintain hand-written CWL files.

The complete maintained starting point is
[`examples/plugins/example_analysis`](examples/plugins/example_analysis).
Copy that package when creating an analysis plugin, then change its package
name and metadata, step declaration, analysis implementation, and
configuration schema.

## Package structure

A minimal analysis plugin contains:

```text
my_asokai_plugin/
├── pyproject.toml
└── src/
    └── my_asokai_plugin/
        ├── __init__.py
        ├── analysis_step.py
        └── config.schema.yaml
```

The plugin imports its supported authoring contracts from `ASOkai.Plugins`:

```python
from ASOkai.Plugins import (
    AnalysisStep,
    CsvFile,
    FileInput,
    FileOutput,
    ScalarParam,
    StepSpec,
)
```

`ASOkai.Plugins` is the public plugin interface. Packages whose names begin
with an underscore, including `ASOkai._pipeline` and `ASOkai._cwl`, are
internal implementation details and should not be imported by plugins.

## Declaring a step

A step subclasses `Step`, `CoreStep`, or `AnalysisStep` and declares one
`StepSpec`. The spec is the source of truth for its scalar parameters, file
inputs, file outputs, compatibility, generated command line, and generated
CWL.

An analysis step normally provides:

- a unique `name` and a useful `description`;
- an `analysis_cls` implementing the scientific analysis;
- `FileInput` values sourced from exact producer outputs;
- one primary CSV `FileOutput`, followed by any additional outputs;
- a `StepSpec` containing those declarations; and
- `analysis_kwargs()` to pass loaded inputs and scalar parameters to the
  analysis class.

See
[`analysis_step.py`](examples/plugins/example_analysis/src/asokai_example_analysis/analysis_step.py)
for a working site-specific example. It also demonstrates typed CSV columns,
configuration-backed scalar parameters, and output path templates.

ASOkai derives dependencies from each `FileInput.source`; contributors do not
maintain a second dependency list. It also generates the internal step CLI and
CWL, creates output parent directories, loads typed inputs, validates written
outputs, and publishes them to their declared destinations.

### External command steps

External executables use the same lifecycle as Python implementations. Build
their argument list in an `ExternalCommandStep` instead of replacing the
generated CWL command:

```python
from ASOkai.Plugins import ExternalCommandStep, FileOutput, StepSpec


class MyToolStep(ExternalCommandStep):
    name = "my-tool"
    description = "Runs an external tool through the shared step lifecycle."
    result_output = FileOutput("result", destination="my-tool/result.json")
    spec = StepSpec(outputs=[result_output])

    def build_command(self, args):
        return [
            "external-tool",
            "--output-format", "json",
            "--output", str(args.result_output),
        ]
```

The common `run_cli()` implementation parses the declared arguments, invokes
the external command, and validates every declared output before reporting
success. Generated CWL always dispatches registered steps through this
lifecycle.

## Registering components

Register each contributed class in the corresponding entry-point group. The
entry-point name must exactly match the class's `name`, and the class must be
constructible without arguments.

```toml
[project.entry-points."asokai.steps"]
my-analysis = "my_asokai_plugin.analysis_step:MyAnalysisStep"

[project.entry-points."asokai.tasks"]
my-task = "my_asokai_plugin.task:MyTask"

[project.entry-points."asokai.workflows"]
my-workflow = "my_asokai_plugin.workflow:MyWorkflow"
```

Only declare the groups the package actually contributes. A task contains
registered step instances. A workflow contains registered steps, tasks, or
other workflows. ASOkai validates these references when it builds the pipeline
catalog. See the
[pipeline-component guide](docs/source/contributor-guide/guides/Pipeline-components.rst)
for their composition contracts.

## Adding configuration

If a step uses plugin-owned configuration paths, package a YAML schema and
register its path:

```python
# my_asokai_plugin/__init__.py
from pathlib import Path

CONFIG_SCHEMA_PATH = Path(__file__).with_name("config.schema.yaml")
```

```toml
[project.entry-points."asokai.config_schemas"]
my-plugin = "my_asokai_plugin:CONFIG_SCHEMA_PATH"

[tool.setuptools.package-data]
my_asokai_plugin = ["config.schema.yaml"]
```

The schema describes only configuration owned by the plugin. Inputs sourced
from another step already inherit that producer's contract and configuration.
ASOkai validates the complete merged configuration against every registered
schema, so a plugin schema must permit top-level namespaces it does not own.
It should reject unknown properties inside its own namespace so misspelled
settings fail validation.
Override `validate_parameters()` only for relationships between resolved
parameter values that a YAML schema cannot express clearly.

## Installing and checking a plugin

Install the package into the same Conda environment as ASOkai:

```bash
python -m pip install -e /path/to/my_asokai_plugin
```

ASOkai then discovers it automatically:

```bash
ASOkai list steps
ASOkai describe step my-analysis
ASOkai run --step my-analysis --config-file config.yaml
```

Before publishing, check that:

- every entry-point name matches the declared component name;
- every contributed class can be instantiated without arguments;
- file inputs reuse exact registered producer outputs;
- every referenced configuration path exists in ASOkai's schema or the
  plugin's schema;
- output filenames distinguish parameter values that change their contents;
- the plugin's tests pass with the supported ASOkai version; and
- installing the wheel includes `config.schema.yaml` and any other package
  data.

Installed plugins are not inserted into ASOkai's static documentation. Each
plugin owns its documentation build and decides which declarations to publish.
