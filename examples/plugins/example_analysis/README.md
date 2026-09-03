# Example ASOkai analysis plugin

This directory is a complete, installable external plugin. It demonstrates one
analysis step and one plugin-owned configuration field without modifying the
ASOkai package.

From this directory, install the plugin into the environment containing ASOkai:

```bash
python -m pip install -e .
```

ASOkai then discovers the step through the entry points in `pyproject.toml`:

```bash
ASOkai list steps
```

Add the plugin setting to the ASOkai configuration:

```yaml
example_analysis:
  minimum_length: 16
```

The step can then be selected like any built-in analysis:

```bash
ASOkai run --step example-sequence-length --config-file config.yaml
```

The `StepSpec` in `analysis_step.py` is the step contract. The YAML schema only
describes the plugin-owned configuration values, and `pyproject.toml` makes the
step and schema discoverable after installation. A step may override
`validate_parameters` when it needs a relationship between scalar parameters
that the YAML schema cannot express.

The schema permits unrelated settings at its root because ASOkai passes the
complete merged configuration to every registered schema. It rejects unknown
settings inside `example_analysis`, the namespace owned by this plugin.

Installed plugins are not added to ASOkai's static documentation. The plugin
remains responsible for its own documentation build and example configuration.
