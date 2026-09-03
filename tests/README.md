# ASOkai Test Suite

Tests cover the ASOkai domain model, serialization layer, KMC command wrappers,
and the CWL-backed pipeline orchestration code.

## Structure

- `unit/` covers individual domain, utility, contract, pipeline, CWL, and CLI
  components with external work isolated or mocked.
- `integration/` executes a synthetic pipeline through the supported CWL
  engines and verifies publication behavior.
- `plugins/` covers the public plugin API, entry-point discovery, validation,
  and the checked-in example plugin.
- `contributor/` enforces repository and extension-authoring conventions.
- `docs/` verifies generated API and pipeline contract references.
- `fixtures/` contains static files used by CWL and publication tests.

## Running Tests

```bash
conda run -n ASOkai pytest
```

Run individual files or tests with standard pytest selectors:

```bash
conda run -n ASOkai pytest tests/unit/test_runner.py
conda run -n ASOkai pytest tests/unit/test_cli_main.py::test_run_requires_explicit_runnable_selection
```

The directory layout is the primary test selector. Integration tests also
carry an explicit marker because they require installed CWL executables:

```bash
conda run -n ASOkai pytest -m "not integration"
conda run -n ASOkai pytest -m integration
```

`pytest-cov` is not required by the current environment. Install it separately
before using coverage flags.

## Coverage Areas

- Serialization contracts: `Serializable`, `Bio.Seq.Seq`,
  `GenomeUtils.Locus`, nested containers, and typed `JsonFile` roundtrips.
- Domain objects: genomic and transcript sites, target genes, antisense
  therapeutics, candidate generation, site IDs, edge coordinates, special
  identifiers, and empty inputs.
- KMC wrappers: executable resolution, command-line construction, validation,
  subprocess failure handling, output handles, and KMC tools operations.
- Pipeline configuration: YAML loading, dotted-key resolution, and CLI override
  application.
- Pipeline planning: task/workflow step expansion, automatic dependency
  ordering, run deduplication, valid-output reuse, non-recursive failure, and
  cycle detection.
- Runner and CWL generation: input resolution precedence, dependency wiring,
  reused file inputs, fixed output arguments, dry-run behavior, CWL
  export, publication layouts, and normalized CWL step IDs.
- End-to-end execution: shared-run planning, generated CWL execution, and
  publication through a small local synthetic workflow.
- CLI: listing and describing registered units, hidden internal step dispatch,
  run selection defaults, unknown runnable errors, config override parsing, and
  YAML scalar preservation.
- Step entrypoints: parser-level validation and mocked execution paths for
  genome download, target-gene creation, candidate generation, and analysis
  without network or large-genome work.
- Plugin and contributor contracts: public imports, entry-point validation,
  dependency registration, package-owned schemas, and analysis-step authoring.
- Documentation generation: registry-derived references, source tracking,
  configuration descriptions, JSON contracts, and valid generated examples.

## Fixtures

The shared `sample_sequence` fixture provides a representative `Bio.Seq.Seq`.
Tests use pytest's `tmp_path` and `monkeypatch` fixtures directly so filesystem
and process state remain isolated within each test.

## Expectations

All tests should be deterministic and local. Unit tests mock external tools,
network downloads, CWL execution, and heavy genome construction. Integration
tests use only local synthetic data but invoke the installed CWL engines.
