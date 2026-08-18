# ASOkai

ASOkai is designed to provide analytical features from different aspects around ASO drug design, commonly used attributes like GC content as well as attributes usually requiring human experts. In particular, our focus is on extensive analysis of specific and unspecific off-targets and their impact on potential target knockdown evaluated through kinetic simulations.
While the pipeline can be utilised as a ready-to-use workflow, its modularity enables the user to use any individual analytical step individually and integrate them in already existing user-defined drug design workflows. The frame work is open-source.

## Antisense therapeutic sequences

ASOkai represents nucleotide sequences with `T`, not `U`.

For every `AntisenseTherapeutic`, the `sequence` property returns the
antisense-strand sequence used for target recognition. For a multi-stranded
therapeutic such as siRNA, it does not combine the antisense and sense strands;
the sense-strand sequence is available separately as `sense_strand.sequence`.

Candidate generation writes therapeutics and their site bindings to separate
files. Each binding stores a therapeutic ID and a site ID.

The candidate-generation step supports unmodified DNA ASOs and wing-gap-wing
gapmer ASOs. The standard configuration selects an RNase-H1 gapmer:

```yaml
antisense:
  modality: aso
  mechanism: rnase-h1
  design:
    type: gapmer
    left_wing_length: 3
    gap_length: 10
    right_wing_length: 3
```

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

Configure single-node execution resource requests under `resources`:

```yaml
resources:
  default:
    n_processes: 1
    memory_mb: 4096
  intrinsic-features:
    n_processes: 4
```

Missing per-step fields inherit from `resources.default`; if the entire section
is omitted, ASOkai uses 4096 MiB and one process where multiprocessing is
supported. Single-process steps always request one core and reject a step-level
`n_processes` setting. `memory_mb` is measured in MiB. ASOkai translates these
values to the CWL `ResourceRequirement` fields `coresMin` and `ramMin`.

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
|   └── intrinsic-features
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

## Contributor setup

Create the Conda environment so binary dependencies such as KMC are managed by
Conda, then install ASOkai and its contributor tools into that environment:

```bash
conda env create -f environment.yaml
conda activate ASOkai
python -m pip install -e ".[dev]"
```

## Documentation

To build the document using sphinx, run:
`sphinx-build -M html docs/source docs/build`

## License

This software is under L-GPL-3.0-later.

Copyright 2026 Alexander Schliep
