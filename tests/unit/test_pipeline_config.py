#!/usr/bin/env python
"""
Filename: tests/unit/test_pipeline_config.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for pipeline config loading and resolution.
License: LGPL-3.0-or-later
"""

from pathlib import Path

import pytest

from ASOkai.Plugins import (
    FileInput,
    FileOutput,
    OutputPathTemplate,
    RunSpec,
    ScalarParam,
    Step,
    StepSpec,
    TemplateField,
)
from ASOkai._pipeline import config as cfg
from ASOkai._pipeline.contracts.execution import StepRun
from ASOkai._pipeline.steps.analysis.intrinsic_features import (
    IntrinsicFeaturesStep,
)
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep
from ASOkai._pipeline.steps.core.generate_aso_candidates import (
    GenerateASOCandidatesStep,
)
from ASOkai._pipeline.tasks.base import Task


@pytest.fixture
def sample_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "datadir: ./data\n"
        "genome:\n"
        "  assembly_id: GRCh38\n"
        "  ensembl_release: 114\n"
        "  species: Homo_sapiens\n"
    )
    return config_file


def test_load_reads_a_yaml_mapping(sample_config):
    config = cfg.load(sample_config)
    assert config["datadir"] == "./data"
    assert config["genome"]["assembly_id"] == "GRCh38"


@pytest.mark.parametrize(
    "runs",
    [
        [],
        [{"step": "download-genome", "task": "instantiate-target-gene"}],
        [{"step": "download-genome", "parameters": {"mode": ["fast"]}}],
        [{"step": "download-genome", "inputs": {}}],
        [{"task": "instantiate-target-gene", "id": "named"}],
        [{"task": "instantiate-target-gene", "inputs": {"reference": {"path": "a.fa"}}}],
        [{"id": "1", "step": "download-genome"}],
        [{"step": "download-genome", "inputs": {"reference": {"run_id": "named"}}}],
        [{"step": "download-genome", "inputs": {"reference": {"path": "a.fa", "run_id": "named", "output": "reference"}}}],
        [{"step": "download-genome", "inputs": {"reference": {"run": "named", "output": "reference"}}}],
    ],
)
def test_config_schema_rejects_invalid_run_declarations(tmp_path, runs):
    with pytest.raises(ValueError, match="runs"):
        cfg.validate_config_schema(
            {"datadir": str(tmp_path), "runs": runs},
            plugin_schema_paths={},
        )


def test_config_schema_accepts_task_parameter_overrides(tmp_path):
    cfg.validate_config_schema(
        {
            "datadir": str(tmp_path),
            "runs": [{"task": "build-index", "parameters": {"k": 21}}],
        },
        plugin_schema_paths={},
    )


@pytest.mark.parametrize("path", ["target.k", "missing.task_value"])
def test_task_parameter_fallback_path_requires_registered_schema(path):
    task_type = type(
        "_TaskWithFallback",
        (Task,),
        {
            "name": "task-with-fallback",
            "description": "Forwards a configured value.",
            "params": (ScalarParam("site_length", int, config=path),),
            "runs": (
                RunSpec(
                    "gene",
                    CreateTargetGeneStep(),
                    parameters={"k": {"task_parameter": "site_length"}},
                ),
            ),
        },
    )

    if path == "target.k":
        cfg.validate_task_config_paths([task_type()])
    else:
        with pytest.raises(ValueError, match="missing.task_value"):
            cfg.validate_task_config_paths([task_type()])


@pytest.mark.parametrize("content", ["", "- one\n- two\n"])
def test_load_rejects_non_mapping_root(tmp_path, content):
    path = tmp_path / "config.yaml"
    path.write_text(content)

    with pytest.raises(ValueError, match="mapping at its root"):
        cfg.load(path)


def test_load_rejects_invalid_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("genome: [")

    with pytest.raises(ValueError, match="Invalid YAML configuration"):
        cfg.load(path)


def test_output_path_config_must_be_declared_in_a_schema():
    class UndeclaredOutputConfigStep(Step):
        name = "undeclared-output-config"
        description = "Uses an undeclared value only for its destination."
        result_output = FileOutput(
            "result",
            destination=OutputPathTemplate(
                "{label}.txt",
                fields={"label": TemplateField("missing.label")},
            ),
        )
        spec = StepSpec(outputs=[result_output])

    with pytest.raises(ValueError, match=r"missing.label.*no registered"):
        cfg.validate_step_config_paths([UndeclaredOutputConfigStep()])


def test_resolve_top_level(sample_config):
    config = cfg.load(sample_config)
    assert cfg.resolve(config, "datadir") == "./data"


def test_resolve_nested(sample_config):
    config = cfg.load(sample_config)
    assert cfg.resolve(config, "genome.assembly_id") == "GRCh38"
    assert cfg.resolve(config, "genome.ensembl_release") == 114


def test_resolve_missing_key(sample_config):
    config = cfg.load(sample_config)
    with pytest.raises(KeyError, match="genome.nonexistent"):
        cfg.resolve(config, "genome.nonexistent")


def test_apply_overrides(sample_config):
    config = cfg.load(sample_config)
    cfg.apply_overrides(config, {"genome.ensembl_release": 115})
    assert config["genome"]["ensembl_release"] == 115


def test_apply_overrides_new_key(sample_config):
    config = cfg.load(sample_config)
    cfg.apply_overrides(config, {"genome.new_key": "value"})
    assert config["genome"]["new_key"] == "value"


def test_apply_overrides_rejects_scalar_parent(sample_config):
    config = cfg.load(sample_config)

    with pytest.raises(ValueError, match="cannot descend.*assembly_id"):
        cfg.apply_overrides(
            config,
            {"genome.assembly_id.version": 2},
        )


def test_schema_validation_is_separate_from_loading(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "datadir: ./data\n"
        "genome:\n"
        "  source: ''\n"
    )

    config = cfg.load(path)

    with pytest.raises(ValueError, match=r"genome.source"):
        cfg.validate_config_schema(config)


def test_output_validation_policy_defaults_to_receipts(tmp_path):
    config = {"datadir": str(tmp_path)}

    cfg.validate_config_schema(config)

    assert cfg.output_validation_mode(config) == "signature"


def test_output_validation_policy_accepts_only_supported_modes(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "validation": {"existing_outputs": "contract"},
    }

    cfg.validate_config_schema(config)
    assert cfg.output_validation_mode(config) == "contract"

    config["validation"]["existing_outputs"] = "full"
    with pytest.raises(ValueError, match="existing_outputs.*one of"):
        cfg.validate_config_schema(config)


def test_config_schema_leaves_supported_values_to_selected_steps(tmp_path):
    cfg.validate_config_schema(
        {
            "datadir": str(tmp_path),
            "antisense": {
                "modality": "sirna",
                "mechanism": "risc",
                "design": {"type": "custom"},
            },
        }
    )


def test_selected_step_rejects_an_unsupported_design(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "GRCh38",
            "ensembl_release": 114,
            "source": "ensembl",
            "species": "Homo_sapiens",
        },
        "target": {
            "target_id": "ENSG1",
            "k": 16,
            "region": "pre-mrna",
        },
        "antisense": {
            "modality": "aso",
            "mechanism": "rnase-h1",
            "design": {"type": "custom"},
        },
    }

    with pytest.raises(
        ValueError,
        match=r"antisense.design.type.*unmodified.*gapmer",
    ):
        cfg.validate_step_config(
            config,
            [GenerateASOCandidatesStep()],
        )


def test_selected_step_accepts_an_unmodified_aso_design(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "GRCh38",
            "ensembl_release": 114,
            "source": "ensembl",
            "species": "Homo_sapiens",
        },
        "target": {
            "target_id": "ENSG1",
            "k": 16,
            "region": "pre-mrna",
        },
        "antisense": {
            "modality": "aso",
            "mechanism": "rnase-h1",
            "design": {"type": "unmodified"},
        },
    }

    cfg.validate_config_schema(config)
    cfg.validate_step_config(
        config,
        [GenerateASOCandidatesStep()],
    )


def test_aso_step_rejects_a_different_modality(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "genome": {"assembly_id": "GRCh38"},
        "target": {
            "target_id": "ENSG1",
            "k": 16,
            "region": "pre-mrna",
        },
        "antisense": {
            "modality": "sirna",
            "mechanism": "rnase-h1",
            "design": {"type": "unmodified"},
        },
    }

    with pytest.raises(
        ValueError,
        match=r"antisense.modality.*incompatible.*generate-aso-candidates",
    ):
        cfg.validate_step_config(config, [GenerateASOCandidatesStep()])


def test_config_schema_allows_plugin_namespaces(tmp_path):
    cfg.validate_config_schema(
        {
            "datadir": str(tmp_path),
            "example_plugin": {
                "threshold": 0.5,
            },
        }
    )


def test_configured_step_names_must_be_registered(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "steps": {"misspelled-step": {"inputs": {}}},
        "resources": {"another-misspelled-step": {"memory_mb": 1024}},
    }

    with pytest.raises(ValueError) as raised:
        cfg.validate_configured_step_names(
            config,
            {"intrinsic-features": IntrinsicFeaturesStep()},
        )

    message = str(raised.value)
    assert "$.steps.misspelled-step" in message
    assert "$.resources.another-misspelled-step" in message


def test_configured_input_name_must_be_declared_by_step(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "steps": {
            "intrinsic-features": {
                "inputs": {"misspelled_input": {"path_override": "x"}},
            },
        },
    }

    with pytest.raises(ValueError, match="misspelled_input"):
        cfg.validate_configured_step_names(
            config,
            {"intrinsic-features": IntrinsicFeaturesStep()},
        )


@pytest.mark.parametrize(
    "input_configuration",
    [
        {},
        {"parameters": {}},
        {
            "path_override": "target.json",
            "parameters": {"region": "pre-mrna"},
        },
    ],
)
def test_config_schema_rejects_invalid_step_input_configuration(
    tmp_path,
    input_configuration,
):
    with pytest.raises(ValueError, match="intrinsic-features.*target_gene"):
        cfg.validate_config_schema(
            {
                "datadir": str(tmp_path),
                "steps": {
                    "intrinsic-features": {
                        "inputs": {
                            "target_gene": input_configuration,
                        },
                    },
                },
            }
        )


def test_config_schema_uses_installed_plugin_schemas(
    tmp_path,
    monkeypatch,
):
    schema_path = tmp_path / "config.schema.yaml"
    schema_path.write_text(
        "type: object\n"
        "properties:\n"
        "  example_plugin:\n"
        "    type: object\n"
        "    properties:\n"
        "      threshold:\n"
        "        type: number\n"
        "        maximum: 1\n"
    )
    monkeypatch.setattr(
        "ASOkai._pipeline.catalog.get_config_schema_paths",
        lambda: {"example": schema_path},
    )

    with pytest.raises(
        ValueError,
        match=r"Plugin 'example' schema.*example_plugin.threshold",
    ):
        cfg.validate_config_schema(
            {
                "datadir": str(tmp_path),
                "example_plugin": {
                    "threshold": 2,
                },
            }
        )


def test_validate_step_config_uses_defaults_and_only_selected_steps(
    sample_config,
):
    config = cfg.load(sample_config)
    step = DownloadGenomeStep()

    cfg.validate_step_config(config, [step])

    run = StepRun(step.name, step, config)
    assert run.output_path(step.dna_output).parts[-4] == "ensembl"


def test_validate_step_config_requires_selected_step_parameters(tmp_path):
    with pytest.raises(ValueError) as raised:
        cfg.validate_step_config(
            {"datadir": str(tmp_path)},
            [DownloadGenomeStep()],
        )

    message = str(raised.value)
    assert "$.genome.assembly_id" in message
    assert "$.genome.ensembl_release" in message
    assert "$.genome.species" in message
    assert "$.genome.source" not in message


def test_config_schema_reports_all_errors(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "",
            "ensembl_release": 0,
            "species": "Homo_sapiens",
        },
    }

    with pytest.raises(ValueError) as raised:
        cfg.validate_config_schema(config)

    message = str(raised.value)
    assert "$.genome.assembly_id" in message
    assert "$.genome.ensembl_release" in message


def test_config_schema_requires_one_target_identifier(
    tmp_path,
):
    config = {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "GRCh38",
            "ensembl_release": 114,
            "species": "Homo_sapiens",
        },
        "target": {
            "k": 16,
            "region": "pre-mrna",
        },
    }

    with pytest.raises(
        ValueError,
        match=r"exactly one.*target.target_id, target.target_name",
    ):
        cfg.validate_config_schema(config)


def test_config_schema_rejects_two_target_identifiers(tmp_path):
    with pytest.raises(
        ValueError,
        match=r"exactly one.*target.target_id, target.target_name",
    ):
        cfg.validate_config_schema(
            {
                "datadir": str(tmp_path),
                "target": {
                    "target_id": "ENSG1",
                    "target_name": "KRAS",
                },
            }
        )


@pytest.mark.parametrize(
    "field",
    ["left_wing_length", "gap_length", "right_wing_length"],
)
@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "3"])
def test_config_schema_rejects_invalid_gapmer_segment_lengths(field, value):
    with pytest.raises(ValueError, match=rf"antisense.design.{field}"):
        cfg.validate_config_schema(
            {
                "datadir": ".",
                "antisense": {
                    "design": {
                        "type": "gapmer",
                        "left_wing_length": 3,
                        "gap_length": 10,
                        "right_wing_length": 3,
                        field: value,
                    }
                },
            }
        )


@pytest.mark.parametrize(
    "missing_field",
    ["left_wing_length", "gap_length", "right_wing_length"],
)
def test_config_schema_requires_every_gapmer_segment_length(missing_field):
    design = {
        "type": "gapmer",
        "left_wing_length": 3,
        "gap_length": 10,
        "right_wing_length": 3,
    }
    del design[missing_field]

    with pytest.raises(ValueError, match=rf"antisense.design.*{missing_field}"):
        cfg.validate_config_schema(
            {
                "datadir": ".",
                "antisense": {"design": design},
            }
        )


def test_config_schema_rejects_gapmer_lengths_for_unmodified_aso():
    with pytest.raises(ValueError, match="antisense.design"):
        cfg.validate_config_schema(
            {
                "datadir": ".",
                "antisense": {
                    "design": {
                        "type": "unmodified",
                        "gap_length": 10,
                    }
                },
            }
        )


def test_selected_step_requires_gapmer_segments_to_match_target_length(
    tmp_path,
):
    config = {
        "datadir": str(tmp_path),
        "genome": {"assembly_id": "GRCh38"},
        "target": {
            "target_id": "ENSG1",
            "k": 18,
            "region": "pre-mrna",
        },
        "antisense": {
            "modality": "aso",
            "mechanism": "rnase-h1",
            "design": {
                "type": "gapmer",
                "left_wing_length": 3,
                "gap_length": 10,
                "right_wing_length": 3,
            },
        },
    }

    cfg.validate_config_schema(config)
    with pytest.raises(
        ValueError,
        match=r"generate-aso-candidates.*target-site length \(18\)",
    ):
        cfg.validate_step_config(
            config,
            [GenerateASOCandidatesStep()],
        )


@pytest.mark.parametrize(
    ("create_override", "message"),
    [
        (False, "file does not exist"),
        (True, "path is not a file"),
    ],
)
def test_validate_step_config_rejects_invalid_override_path(
    tmp_path,
    create_override,
    message,
):
    override = tmp_path / "target.json"
    if create_override:
        override.mkdir()
    config = {
        "datadir": str(tmp_path),
        "genome": {"assembly_id": "GRCh38"},
        "target": {
            "target_id": "ENSG1",
            "k": 16,
            "region": "pre-mrna",
        },
        "steps": {
            "generate-aso-candidates": {
                "inputs": {
                    "target_gene": {
                        "path_override": str(override),
                    },
                },
            },
        },
        "antisense": {
            "modality": "aso",
            "mechanism": "rnase-h1",
            "design": {
                "type": "gapmer",
                "left_wing_length": 3,
                "gap_length": 10,
                "right_wing_length": 3,
            },
        },
    }

    with pytest.raises(ValueError, match=message):
        cfg.validate_step_config(
            config,
            [GenerateASOCandidatesStep()],
        )


def test_validate_step_config_checks_override_file_contents(tmp_path):
    override = tmp_path / "target.json"
    override.write_text("{not-json")
    config = {
        "datadir": str(tmp_path),
        "genome": {"assembly_id": "GRCh38"},
        "target": {
            "target_id": "ENSG1",
            "k": 16,
            "region": "pre-mrna",
        },
        "steps": {
            "generate-aso-candidates": {
                "inputs": {
                    "target_gene": {"path_override": str(override)},
                },
            },
        },
        "antisense": {
            "modality": "aso",
            "mechanism": "rnase-h1",
            "design": {
                "type": "gapmer",
                "left_wing_length": 3,
                "gap_length": 10,
                "right_wing_length": 3,
            },
        },
    }

    with pytest.raises(ValueError, match="Invalid JSON"):
        cfg.validate_step_config(
            config,
            [GenerateASOCandidatesStep()],
        )


def test_validate_step_config_checks_configured_producer_parameter_type(
    tmp_path,
):
    class ConfiguredConsumerStep(Step):
        name = "consumer"
        description = ""
        spec = StepSpec(
            inputs=[
                FileInput(
                    "target_gene",
                    source=CreateTargetGeneStep.target_gene_output,
                    configurable_parameters=("region",),
                ),
            ],
        )
    config = {
        "datadir": str(tmp_path),
        "steps": {
            "consumer": {
                "inputs": {
                    "target_gene": {"parameters": {"region": 3}},
                },
            },
        },
    }

    with pytest.raises(
        ValueError,
        match=r"steps.consumer.inputs.target_gene.parameters.region.*must be one of",
    ):
        cfg.validate_step_config(config, [ConfiguredConsumerStep()])


def test_validate_step_config_rejects_datadir_file(tmp_path):
    datadir = tmp_path / "data"
    datadir.touch()

    with pytest.raises(ValueError, match="datadir.*not a directory"):
        cfg.validate_step_config(
            {
                "datadir": str(datadir),
                "genome": {
                    "assembly_id": "GRCh38",
                    "ensembl_release": 114,
                    "species": "Homo_sapiens",
                },
            },
            [DownloadGenomeStep()],
        )


def test_step_resources_returns_supported_fields():
    step = IntrinsicFeaturesStep()
    config = {
        "resources": {
            step.name: {
                "n_threads": 4,
                "memory_mb": 8192,
            }
        }
    }

    assert cfg.step_resources(config, step) == {
        "n_threads": 4,
        "memory_mb": 8192,
    }


def test_step_resources_uses_builtin_defaults_without_configuration():
    analysis = IntrinsicFeaturesStep()
    download = DownloadGenomeStep()

    assert cfg.step_resources({}, analysis) == {
        "n_threads": 1,
        "memory_mb": 4096,
    }
    assert cfg.step_resources({"resources": {}}, download) == {
        "memory_mb": 4096,
    }


def test_step_resources_merges_configured_defaults_and_step_overrides():
    analysis = IntrinsicFeaturesStep()
    download = DownloadGenomeStep()
    config = {
        "resources": {
            "default": {
                "n_threads": 2,
                "memory_mb": 2048,
            },
            analysis.name: {"n_threads": 8},
        }
    }

    assert cfg.step_resources(config, analysis) == {
        "n_threads": 8,
        "memory_mb": 2048,
    }
    assert cfg.step_resources(config, download) == {
        "memory_mb": 2048,
    }


def test_selected_step_rejects_unsupported_thread_setting(
    sample_config,
):
    config = cfg.load(sample_config)
    config["resources"] = {
        "download-genome": {"n_threads": 2},
    }
    cfg.validate_config_schema(config)

    with pytest.raises(
        ValueError,
        match=r"resources.download-genome.n_threads.*does not support",
    ):
        cfg.validate_step_config(config, [DownloadGenomeStep()])


def test_default_thread_setting_is_only_applied_to_supported_steps(
    sample_config,
):
    config = cfg.load(sample_config)
    config["resources"] = {
        "default": {"n_threads": 4},
    }

    cfg.validate_config_schema(config)
    cfg.validate_step_config(config, [DownloadGenomeStep()])
    assert cfg.step_resources(config, DownloadGenomeStep()) == {
        "memory_mb": 4096,
    }


@pytest.mark.parametrize("section", ["default", "analysis"])
def test_config_schema_rejects_unsupported_resource_fields(section):
    config = {
        "datadir": ".",
        "resources": {section: {"nodes": 2}},
    }

    with pytest.raises(ValueError, match=rf"resources.{section}.*nodes"):
        cfg.validate_config_schema(config)


@pytest.mark.parametrize("key", ["n_threads", "memory_mb"])
@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "4"])
def test_config_schema_rejects_invalid_resource_values(key, value):
    config = {
        "datadir": ".",
        "resources": {"analysis": {key: value}},
    }

    with pytest.raises(ValueError, match=rf"resources.analysis.{key}"):
        cfg.validate_config_schema(config)


@pytest.mark.parametrize("section", ["default", "intrinsic-features"])
@pytest.mark.parametrize("also_sets_threads", [False, True])
def test_config_schema_explains_thread_setting_migration(section, also_sets_threads):
    resource_values = {"n_processes": 4}
    if also_sets_threads:
        resource_values["n_threads"] = 2
    config = {"datadir": ".", "resources": {section: resource_values}}

    with pytest.raises(
        ValueError,
        match=rf"resources\.{section}\.n_processes: renamed to n_threads; "
        rf"use resources\.{section}\.n_threads instead",
    ):
        cfg.validate_config_schema(config)


@pytest.mark.parametrize(
    "resources",
    [[], {"analysis": 4}, {"default": 4}],
)
def test_config_schema_rejects_non_mapping_resources(resources):
    with pytest.raises(ValueError, match="resources"):
        cfg.validate_config_schema(
            {
                "datadir": ".",
                "resources": resources,
            }
        )
