# CWL Tools & Workflows

CWL (Common Workflow Language) definitions for the ASOkai pipeline, organized by execution level.

## Directory Structure

### `steps/`

Low-level **atomic tools** that wrap individual scripts. Each step corresponds to a single Python script in `scripts/`.

- `download-genome.cwl` — Downloads genome data from Ensembl FTP
- `build-genome.cwl` — Builds genome object
- `create-target-gene-object.cwl` — Creates target gene object
- ...

**Usage:** Steps are generally not intended for direct use by end-users. Use tasks or workflows instead.

### `tasks/`

Mid-level **logical groups** that compose multiple steps to perform a specific analysis task. Tasks manage inputs and outputs between steps automatically and resolve dependencies.

- `instantiate-target-gene.cwl` — Creates and initializes a target gene object (depends on: `steps/download-genome`, `steps/build-genome`, `steps/create-target-gene-object`)
- `intrinsic-features.cwl` — Analyzes intrinsic features (depends on: `tasks/instantiate-target-gene`)
- `specific-off-targets.cwl` — Identifies specific off-target sites (depends on: `tasks/instantiate-target-gene`)
- ...

**Usage:** Users typically interact with tasks via the CLI (`ASOkai run --tasks instantiate-target-gene`).

### `workflows/`

High-level **complete pipelines** that orchestrate multiple tasks and/or steps to produce end-to-end results.

- `standard.cwl` — The standard ASOkai analysis pipeline

**Usage:** Users run workflows for complete analyses (`ASOkai run --workflow standard`).

## Versioning & Compatibility

All CWL files use **v1.2**, which provides:
- Cleaner optional type syntax (`string?` instead of `["null", string]`)
- Network access control (`NetworkAccess`)
- Better error handling and validation

## Path Resolution

When a task or workflow references a step via `run:`, use relative paths from the CWL file's location:

```yaml
# In cwl/tasks/instantiate-target-gene.cwl
steps:
  download:
    run: ../steps/download-genome.cwl
    ...
```

