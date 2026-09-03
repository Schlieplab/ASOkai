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

The same declarations can drive the plugin's own Sphinx reference. Reusing
ASOkai's contract renderer is optional and does not add the plugin to ASOkai's
static documentation; the plugin remains responsible for its documentation
build and example configuration.
