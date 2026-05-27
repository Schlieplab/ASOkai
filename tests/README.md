# ASOkai Test Suite

Tests cover the ASOkai domain model, serialization layer, KMC command wrappers,
and the CWL-backed pipeline orchestration code.

## Structure

```
tests/
├── conftest.py
├── integration/
│   └── test_serialization_integration.py
└── unit/
    ├── test_base_site_functionality.py
    ├── test_cli_main.py
    ├── test_create_target_gene_step.py
    ├── test_cwl_generation.py
    ├── test_download_genome_step.py
    ├── test_executors.py
    ├── test_genomic_site.py
    ├── test_genomic_site_functionality.py
    ├── test_input_resolution.py
    ├── test_intrinsic_features_step.py
    ├── test_kmc.py
    ├── test_kmc_tools.py
    ├── test_pipeline_config.py
    ├── test_plan.py
    ├── test_runner.py
    ├── test_serializer.py
    ├── test_standard_workflow.py
    ├── test_target_creator_functionality.py
    ├── test_target_functionality.py
    ├── test_target_gene.py
    ├── test_target_gene_creator_functionality.py
    ├── test_transcript_site.py
    ├── test_transcript_site_functionality.py
    └── test_type_registrations.py
```

## Running Tests

```bash
conda run -n ASOkai pytest
```

Run individual files or tests with standard pytest selectors:

```bash
conda run -n ASOkai pytest tests/unit/test_runner.py
conda run -n ASOkai pytest tests/unit/test_cli_main.py::test_run_requires_explicit_runnable_selection
```

`pytest-cov` is not required by the current environment. Install it separately
before using coverage flags.

Registered markers are `unit`, `integration`, and `serialization`. The current
suite mostly relies on file layout rather than marker selection, so prefer file
or node selectors unless a marker is present on the tests you want.

## Coverage Areas

- Serialization and type adapters: `Serializable`, `Bio.Seq.Seq`,
  `GenomeUtils.Locus`, nested containers, file I/O, and roundtrip behavior.
- Domain objects: genomic and transcript sites, targets, target genes, target
  creators, site IDs, edge coordinates, special identifiers, and empty inputs.
- Integration workflows: larger serialization roundtrips, repeated save/load
  cycles, backward-compatible missing attributes, and larger target genes.
- KMC wrappers: executable resolution, command-line construction, validation,
  subprocess failure handling, output handles, and KMC tools operations.
- Pipeline configuration: YAML loading, dotted-key resolution, and CLI override
  application.
- Pipeline planning: runnable flattening, task/workflow expansion, dependency
  ordering, deduplication, recursive dependencies, pre-resolved outputs, and
  cycle detection.
- Runner and CWL generation: input resolution precedence, dependency wiring,
  pre-resolved file inputs, output filename injection, dry-run behavior, CWL
  export, final workflow outputs, and normalized CWL step IDs.
- CLI: listing and describing registered units, hidden internal step dispatch,
  run selection defaults, unknown runnable errors, config override parsing, and
  YAML scalar preservation.
- Step entrypoints: parser-level validation and mocked execution paths for
  download and target-gene creation without network or genome work.

## Fixtures

Shared fixtures in `conftest.py` provide representative `Seq`, `Locus`,
temporary JSON files, and temporary directories. Most pipeline tests create
their own config dictionaries with `tmp_path` so generated paths stay isolated.

## Expectations

All tests should be deterministic and local. Unit tests mock external tools,
network downloads, Toil execution, and heavy genome construction.
