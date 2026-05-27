# ASOkai

ASOkai is designed to provide analytical features from different aspects around ASO drug design, commonly used attributes like GC content as well as attributes usually requiring human experts. In particular, our focus is on extensive analysis of specific and unspecific off-targets and their impact on potential target knockdown evaluated through kinetic simulations.
While the pipeline can be utilised as a ready-to-use workflow, its modularity enables the user to use any individual analytical step individually and integrate them in already existing user-defined drug design workflows. The frame work is open-source.

image

Intrinsic Attributes:

- GC content
- Longest T-run
- Longest AT-run

Genome-wide attributes:

- Specific off-targets
- Unspecific off-targets
- Location

Kinetic Attribute:

- Target-level after ASO administration 
- Kinetic models excluding/including off-target presence

Target attributes:

- Secondary target sites
- Target accessibility

## ASOkai CLI

### Configuration

The `ASOkai` CLI is primarily driven by the configuration file (`config.yaml`). This file contains all the necessary parameters for the different workflows, tasks, and steps. Commands allow you to override specific configuration settings directly via command-line arguments.

### Reporting

Most commands support an optional `--report` flag, which generates a summary report for that specific step.

### CLI Structure

The CLI is organized around a central `run` command that can execute the entire pipeline or specific parts of it.

```
ASOkai
├── workflows
|   └── ...
├── tasks
|   ├── instantiate-target-gene
|   ├── repeated-sites
|   ├── site-accessibility
|   ├── site-quality
|   ├── kinetic-model
|   ├── specific-off-targets
|   ├── unspecific-off-targets
|   ├── intrinsic-features
└── steps
    ├── download-genome
    ├── build-genome
    ├── create-target-gene-object
    ├── load-target-gene-object
    ├── generate-results-file
    └── ...
```

---

### 1. `run`

This is the main, high-level command intended for most users. It can execute one or more low-level steps and automatically resolve dependencies between them.

Current native step execution examples:

```bash
# List available units
ASOkai list steps
ASOkai list tasks
ASOkai list workflows

# Describe one unit
ASOkai describe step download-genome
ASOkai describe task prepare-genome
ASOkai describe workflow standard

# Run one step / task / workflow
ASOkai run --steps download-genome
ASOkai run --tasks prepare-genome
ASOkai run --workflow standard

# Preview execution order without running
ASOkai run --steps download-genome --dry-run

# Override config values from CLI directly
ASOkai run --steps download-genome --genome.ensembl_release 115

# Force rerun even if outputs already exist
ASOkai run --steps download-genome --force
```

---

### 2. Workflows

### 3. Tasks

Tasks are logical collections of steps that perform a specific, complex analysis. They manage the inputs and outputs between steps automatically.

**Dependency Handling:** When a task is executed, it automatically checks for its dependencies (e.g., a target gene object). If a dependency already exists, it will be loaded. If not, the task will automatically run the necessary preceding steps to create the dependency.

#### `instantiate-target-gene`

- **Description:** Creates and initializes a target gene object, which is a prerequisite for most analysis tasks.
- **Dependencies:** `steps.download-genome`, `steps.build-genome`, `steps.create-target-gene-object`.

#### Site-wide Analysis Tasks

- `**intrinsic-features`**: Analyzes intrinsic features like GC content, AT/T-runs.
- **Dependencies:** Depends on `tasks.instantiate-target-gene`.

#### Target-wide Analysis Tasks

- `**repeated-sites`**: Analyzes for repeated sites within the target.
- `**site-accessibility**`: Assesses the accessibility of sites in the target.
- `**site-quality**`: Evaluates the quality of potential ASO binding sites.
- `**kinetic-model**`: Runs the kinetic model for the target.
- **Dependencies:** All depend on `tasks.instantiate-target-gene`.

#### Genome-wide Analysis Tasks

- `**specific-off-targets`**: Identifies specific off-target sites.
- `**unspecific-off-targets**`: Identifies unspecific off-target sites.
- **Dependencies:** All depend on `tasks.instantiate-target-gene`.

#### Results

- `**gather-results`**: Gather results of different steps into a single file.

---

### 4. Steps

Steps are the individual, low-level building blocks of the pipeline. They are generally not intended for direct use by end-users, as managing their inputs and outputs can be complex. However, they can be used for manual pipeline execution or debugging.

#### `download-genome`

- **Description:** Downloads a genome using GenomeUtils.

#### `build-genome`

- **Description:** Builds Genome using GenomeUtils.
- **Dependencies:** `steps.download-genome`.

#### `create-target-gene-object`

- **Description:** Creates a data object for the target gene from Genome, and extracts necessary sites.
- **Dependencies:** `steps.build-genome`.

#### `load-target-gene-object`

- **Description:** Loads an existing target gene object from disk.
- **Dependencies:** `steps.create-target-gene-object`.

## Third-party software and licenses

External programs used by some workflows are not installed via `pip` with the ASOkai package. Obtain binaries according to your setup and respect each upstream license.

### KMC

[KMC](https://github.com/refresh-bio/KMC) is GPLv3-only; see the upstream repository for the license text.

## License

This software is under L-GPL-3.0-later.

Copyright 2025 Alexander Schliep
