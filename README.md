# ASOkai

ASOkai is an open-source pipeline for antisense-therapeutic design and
analysis. Its steps can be run individually, grouped into tasks, or composed
into workflows. ASOkai resolves the required upstream steps, validates their
configuration and file contracts, and executes the resulting plan through CWL.

## Installation

Create the Conda environment so that binary dependencies such as KMC and
Bowtie 2 are installed alongside the Python dependencies, then install ASOkai
into it:

```bash
conda env create -f environment.yaml
conda activate ASOkai
python -m pip install -e .
```

## Quick start

Copy the maintained example configuration and inspect the available pipeline
units:

```bash
cp examples/config.example.yaml config.yaml
ASOkai list steps
ASOkai list tasks
ASOkai list workflows
```

Preview or run the standard workflow:

```bash
ASOkai run --workflow standard --dry-run
ASOkai run --workflow standard
```

The [pipeline reference](docs/source/steps/index.rst) documents the built-in
steps from their runtime declarations. The
[example configuration](examples/config.example.yaml) shows the complete
built-in configuration structure.

## Antisense therapeutic sequences

ASOkai represents nucleotide sequences with `T`, not `U`.

For every `AntisenseTherapeutic`, the `sequence` property returns the
antisense-strand sequence used for target recognition. For a multi-stranded
therapeutic such as siRNA, it does not combine the antisense and sense strands;
the sense-strand sequence is available separately as `sense_strand.sequence`.

Candidate generation writes therapeutics and their site bindings to separate
files. Each binding stores a therapeutic ID and a site ID.

The candidate-generation step currently supports unmodified DNA ASOs and
wing-gap-wing gapmer ASOs. The example configuration selects an RNase-H1
gapmer:

```yaml
parameters:
  antisense:
    modality: aso
    mechanism: rnase-h1
    design:
      type: gapmer
      left_wing_length: 3
      gap_length: 10
      right_wing_length: 3
```

## ASOkai CLI

### Configuration

The CLI reads `./config.yaml` when present, including for CLI-selected runs.
Use `--configfile` to select another file. For a CLI-only run, use `--no-config`;
if no `config.yaml` exists, CLI selections also work without that flag. Both
cases use `./data` as the data directory. A file containing `runs` cannot be
combined with CLI selections.
Place `--param PATH=VALUE` before the first selection to set a shared parameter;
omit the `parameters.` prefix. Use the same path after a step or task to override
that run's parameter:

```bash
ASOkai run --no-config --param genome.assembly=GRCh39 --param genome.release=115 \
  --param genome.species=Homo_sapiens --step create-target-gene \
  --param target.target_id=ENSG00000133703 --param target.k=20 \
  --param target.region=transcriptomic
```

Run `ASOkai describe step NAME` to see its parameters, inputs, and outputs.
Add `-v` to see configuration keys, input override options, and output paths.

Single-node resource requests are configured under `resources`:

```yaml
resources:
  default:
    n_threads: 1
    memory_mb: 4096
  compute-intrinsic-features:
    n_threads: 4
```

Missing per-step settings inherit from `resources.default`. If the section is
omitted, ASOkai uses 4096 MiB and one thread where multithreading is
supported. A step without multithreading support requests one core and does
not accept a step-level `n_threads` setting.

For existing configurations, rename `resources.default.n_processes` and
`resources.<step>.n_processes` to `n_threads`. Direct step invocations now use
`--n-threads` in place of `--n-processes`. Python callers and plugins must use
`n_threads` and the step capability flag `supports_multiple_threads`.

### Commands

Use `list` and `describe` instead of relying on a hard-coded catalog; installed
plugins appear in the same commands:

```bash
# List available units
ASOkai list steps
ASOkai list tasks
ASOkai list workflows

# Describe one unit
ASOkai describe step download-genome
ASOkai describe task instantiate-target-gene
ASOkai describe workflow standard

# Run one step, task, or workflow
ASOkai run --step download-genome
ASOkai run --task instantiate-target-gene
ASOkai run --workflow standard

# Run multiple selected units
ASOkai run --step generate-therapeutic-candidates --step compute-intrinsic-features

# Export the selected goals as a CWL job bundle without executing them
ASOkai export --workflow standard

# Include the complete producer closure in the exported bundle
ASOkai export --step compute-intrinsic-features --recursive

# Require dependencies to exist instead of scheduling missing ones
ASOkai run --step compute-intrinsic-features --non-recursive
```

## Third-party software and licenses

External programs used by some workflows are not installed by the Python
package. Obtain binaries according to your setup and respect each upstream
license.

### KMC

[KMC](https://github.com/refresh-bio/KMC) is GPLv3-only; see the upstream
repository for the license text.

### Bowtie 2

[Bowtie 2](https://bowtie-bio.sourceforge.net/bowtie2/manual.shtml) is
[GPLv3 software](https://github.com/BenLangmead/bowtie2/blob/master/LICENSE).
ASOkai invokes its command-line executables but does not distribute or link
against them.

## Contributor setup

Install ASOkai with its contributor-only tools in the Conda environment:

```bash
conda env create -f environment.yaml
conda activate ASOkai
python -m pip install -e ".[dev]"
```

The [contributor guide](docs/source/contributor-guide/index.rst) explains the
pipeline contracts and provides a copyable analysis-step starting point.

## Documentation

Build the documentation with the active environment's Python:

```bash
python -m sphinx -W --keep-going -b html docs/source docs/build/html
```

## License

ASOkai is licensed under LGPL-3.0-or-later.

Copyright 2026 Alexander Schliep
