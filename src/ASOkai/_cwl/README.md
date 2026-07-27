# CWL Export

ASOkai generates CWL (Common Workflow Language) documents from Python pipeline
metadata.

## Step Tools

Low-level CWL `CommandLineTool` documents are generated from each step's
`StepSpec` metadata in `ASOkai._pipeline.steps`. Its declarations are
separated by role:

- `params`: typed scalar `ScalarParam` values.
- `inputs`: `FileInput` values that point directly to producer outputs.
- `outputs`: `FileOutput` values with destination templates and a `FileType`.

ASOkai derives CWL inputs, CWL outputs, command-line parser options, config
keys, and file override keys from that one spec.

Plugin packages should import the supported step-authoring contracts from
`ASOkai.plugin_api`, rather than importing the internal `ASOkai._cwl` package:

```python
from ASOkai.plugin_api import (
    FileInput,
    FileOutput,
    CoreStep,
    JsonFile,
    ScalarParam,
    StepSpec,
)
```

```python
class ProducerStep(CoreStep):
    name = "producer"
    description = "Produces one result."
    result_output = FileOutput(
        "result",
        destination="results/result.json",
        file_type=JsonFile(),
    )
    spec = StepSpec(outputs=[result_output])


class ConsumerStep(CoreStep):
    name = "consumer"
    description = "Consumes the result."
    result_input = FileInput(
        "result",
        source=ProducerStep.result_output,
        override="result.path",
    )
    spec = StepSpec(inputs=[result_input])
```

The file type owns format-specific I/O and validation. `FileType` leaves an
input as a `Path`, `JsonFile` handles JSON, and `CsvFile` handles tabular CSV.
`JsonFile(SomeSerializableClass)` validates against that type's registered
schema before reconstructing it.
The consumer inherits the exact file type from its source output and does not
repeat the format or value class.

Dependencies are not declared separately: `Step.dependencies` is derived from
the producer outputs referenced by its inputs.

Contributors implement `run_from_args(args)` for the step's work. The central
`ASOkai step <name>` command invokes `run_cli` on the registered step; step
modules do not declare a separate `main()` or module path. `run_cli` builds and
parses the generated CLI and creates the parent directory for every declared
output.

The structured `destination` template defines the complete path relative to
`datadir`. The base `Step` derives output paths, existence checks, and cleanup
from this declaration. When a job is generated, the rendered destination's
basename becomes the filename inside the isolated CWL working directory.
ASOkai uses it for the fixed command-line argument and static output glob, so
contributors do not declare a second filename and it is never exposed as a
configurable input in `run.cwl` or `job.yml`.

Generated step files are written into export/run bundles under:

```text
steps/<step-name>.cwl
```

For example:

```text
steps/download-genome.cwl
steps/create-target-gene.cwl
```

## Tasks And Workflows

Tasks and workflows are ASOkai CLI-level collections. They are not exported as
their own CWL files. Export first resolves the selected steps, tasks, and/or
workflow to an execution plan, then writes one top-level `run.cwl`.

Exports always include the full selected runnable, even when outputs already
exist locally. Missing dependencies can be included with `--recursive`.

## CLI

Use `ASOkai export` to write a runnable CWL bundle:

```bash
ASOkai export --steps download-genome create-target-gene --outdir data/jobs
ASOkai export --tasks instantiate-target-gene --outdir data/jobs
ASOkai export --workflow standard --outdir data/jobs
```

Each bundle contains:

- `run.cwl`: generated top-level runtime CWL.
- `publish.cwl`: final output publisher command-line tool.
- `output-layout.yml`: resolved destinations relative to the data directory.
- `steps/*.cwl`: generated step command-line tools.
- `job.yml`: resolved job inputs.
- `README.md`: standalone run instructions.

## Versioning & Compatibility

All CWL files use **v1.2**, which provides:
- Cleaner optional type syntax (`string?` instead of `["null", string]`)
- Network access control (`NetworkAccess`)
- Better error handling and validation

## Path Resolution

Generated jobs reference step tools relative to the bundle root:

```yaml
steps:
  step_download_genome:
    run: steps/download-genome.cwl
    ...
```

`run.cwl` wires every planned step output into one final publisher step. The
publisher recreates the declared hierarchy using hard links where possible and
atomic copies otherwise. The workflow exposes only the resulting top-level
directories, preventing CWL runners from collecting duplicate flat files.

Run an exported bundle with the intended data directory as the CWL output
directory:

```bash
cwltool --outdir /path/to/data run.cwl job.yml
```

ASOkai-managed execution uses `config["datadir"]` for the same argument, so
normal and exported runs follow the same publication path.
