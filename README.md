# ASOkai

ASOkai is designed to provide analytical features from different aspects around ASO drug design, commonly used attributes like GC content as well as attributes usually requiring human experts. In particular, our focus is on extensive analysis of specific and unspecific off-targets and their impact on potential target knockdown evaluated through kinetic simulations.
While the pipeline can be utilised as a ready-to-use workflow, its modularity enables the user to use any individual analytical step individually and integrate them in already existing user-defined drug design workflows. The frame work is open-source.

![image](docs/images/ASOkai_overview.png)

Intrinsic Attributes:
* GC content
* Longest T-run
* Longest AT-run

Genome-wide attributes:
* Specific off-targets
* Unspecific off-targets
* Location 

Kinetic Attribute:
* Target-level after ASO administration 
* Kinetic models excluding/including off-target presence

Target attributes:
* Secondary target sites
* Target accessibility

## ASOkai CLI

### Configuration
The `ASOkai` CLI is primarily driven by the configuration file (`config.yaml`). This file contains all the necessary parameters for the different pipeline stages and groups. Commands allow you to override specific configuration settings directly via command-line arguments.

### Reporting
Most commands support an optional `--report` flag, which generates a summary report for that specific step.

### CLI Structure

The CLI is organized around a central `run` command that can execute the entire pipeline or specific parts of it.

```
ASOkai
├── all
|
├── groups
|   ├── instantiate-target-gene
|   ├── repeated-sites
|   ├── site-accessibility
|   ├── site-quality
|   ├── kinetic-model
|   ├── specific-off-targets
|   ├── unspecific-off-targets
|   ├── intrinsic-features
|   └── gather-results
|
└── stages
    ├── download-genome
    ├── build-genome
    ├── create-target-gene-object
    ├── load-target-gene-object
    ├── generate-results-file
    └── ...
```

---

### 1. `run`

This is the main, high-level command intended for most users.

#### `asokai run --all`
- **Description:** Runs the entire pipeline from start to finish.

#### `asokai run --groups <group_name_1>,<group_name_2>,...`
- **Description:** Runs one or more specified analysis groups.
- **Example:** `asokai run --groups repeated-sites,site-accessibility`

#### `asokai run --stages <stage_name_1>,<stage_name_2>,...`
- **Description:** Runs one or more specific low-level stages.
- **Example:** `asokai run --stages download-genome`

---

### 2. Groups

Groups are logical collections of stages that perform a specific, complex analysis. They manage the inputs and outputs between stages automatically.

**Dependency Handling:** When a group is executed, it automatically checks for its dependencies (e.g., a target gene object). If a dependency already exists, it will be loaded. If not, the group will automatically run the necessary preceding stages to create the dependency.

To run specific groups, use the `run` command with the `--groups` flag, providing a comma-separated list of group names.

`asokai run --groups <group_name_1>,<group_name_2>`

#### `instantiate-target-gene`
- **Description:** Creates and initializes a target gene object, which is a prerequisite for most analysis groups.
- **Dependencies:** `stages.download-genome`, `stages.build-genome`, `stages.create-target-gene-object`.

#### Site-wide Analysis Groups
- **`intrinsic-features`**: Analyzes intrinsic features like GC content, AT/T-runs.
- **Dependencies:** Depends on `groups.instantiate-target-gene`.

#### Target-wide Analysis Groups
- **`repeated-sites`**: Analyzes for repeated sites within the target.
- **`site-accessibility`**: Assesses the accessibility of sites in the target.
- **`site-quality`**: Evaluates the quality of potential ASO binding sites.
- **`kinetic-model`**: Runs the kinetic model for the target.
- **Dependencies:** All depend on `groups.instantiate-target-gene`.

#### Genome-wide Analysis Groups
- **`specific-off-targets`**: Identifies specific off-target sites.
- **`unspecific-off-targets`**: Identifies unspecific off-target sites.
- **Dependencies:** All depend on `groups.instantiate-target-gene`.

#### Results
- **`gather-results`**: Gather results of different stages into a single file.
---

### 3. Stages

Stages are the individual, low-level building blocks of the pipeline. They are generally not intended for direct use by end-users, as managing their inputs and outputs can be complex. However, they can be used for manual pipeline execution or debugging.

To run specific stages, use the `run` command with the `--stages` flag, providing a comma-separated list of stage names.

`asokai run --stages <stage_name_1>,<stage_name_2>`

#### `download-genome`
- **Description:** Downloads a genome using GenomeUtils.

#### `build-genome`
- **Description:** Builds Genome using GenomeUtils.
- **Dependencies:** `stages.download-genome`.

#### `create-target-gene-object`
- **Description:** Creates a data object for the target gene from Genome, and extracts necessary sites.
- **Dependencies:** `stages.build-genome`.

#### `load-target-gene-object`
- **Description:** Loads an existing target gene object from disk.
- **Dependencies:** `stages.create-target-gene-object`.

## License

This software is under L-GPL-3.0-later.

Copyright 2025 Alexander Schliep