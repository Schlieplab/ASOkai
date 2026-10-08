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
from ASOkai._pipeline.steps.core.generate_therapeutic_candidates import (
    GenerateTherapeuticCandidatesStep,
)


@pytest.fixture
def sample_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "datadir: ./data\n"
        "parameters:\n"
        "  genome:\n"
        "    assembly: GRCh38\n"
        "    release: 114\n"
        "    species: Homo_sapiens\n"
    )
    return config_file


def test_load_reads_a_yaml_mapping(sample_config):
    config = cfg.load(sample_config)
    assert config["datadir"] == "./data"
    assert config["parameters"]["genome"]["assembly"] == "GRCh38"


@pytest.mark.parametrize(
    "runs",
    [
        [],
        [{"step": "download-genome", "task": "instantiate-target-gene"}],
        [{"step": "download-genome", "parameters": {"mode": ["fast"]}}],
        [{"step": "download-genome", "inputs": {}}],
        [{"task": "instantiate-target-gene", "runs": [{"parameters": {"k": 21}}]}],
        [
            {
                "task": "instantiate-target-gene",
                "inputs": {"reference": {"path": "a.fa"}},
            }
        ],
        [{"id": "1", "step": "download-genome"}],
        [{"step": "download-genome", "inputs": {"reference": {"from_run": "named"}}}],
        [
            {
                "step": "download-genome",
                "inputs": {"reference": {"from_run": "named", "output": "reference"}},
            }
        ],
        [
            {
                "step": "download-genome",
                "inputs": {
                    "reference": {
                        "path": "a.fa",
                        "from": "run.named.reference",
                    }
                },
            }
        ],
        [
            {
                "step": "download-genome",
                "inputs": {"reference": {"run": "named", "output": "reference"}},
            }
        ],
    ],
)
def test_config_schema_rejects_invalid_run_declarations(tmp_path, runs):
    with pytest.raises(ValueError, match="runs"):
        cfg.validate_config_schema(
            {"datadir": str(tmp_path), "runs": runs},
            plugin_schema_paths={},
        )


def test_config_schema_accepts_task_and_child_run_overrides(tmp_path):
    cfg.validate_config_schema(
        {
            "datadir": str(tmp_path),
            "runs": [
                {
                    "task": "build-index",
                    "id": "index",
                    "parameters": {"k": 21},
                    "runs": [
                        {
                            "id": "gene",
                            "parameters": {"region": "exonic"},
                            "inputs": {"source": {"from": "run.reference.result"}},
                        }
                    ],
                }
            ],
        },
        plugin_schema_paths={},
    )


def test_config_schema_accepts_shared_parameters_and_from_inputs(tmp_path):
    cfg.validate_config_schema(
        {
            "datadir": str(tmp_path),
            "parameters": {
                "genome": {
                    "assembly": "GRCh38",
                    "release": 114,
                    "species": "Homo_sapiens",
                },
                "target": {"target_name": "KRAS", "k": 21},
            },
            "validation": {"existing_outputs": "signature"},
            "resources": {"default": {"n_workers": 2}},
            "runs": [
                {"step": "create-target-gene", "id": "gene"},
                {
                    "step": "compute-intrinsic-features",
                    "inputs": {"target_gene": {"from": "run.gene.target_gene"}},
                },
            ],
        },
        plugin_schema_paths={},
    )


def test_config_schema_rejects_legacy_root_parameter_group(tmp_path):
    with pytest.raises(ValueError, match="move this group under parameters.target"):
        cfg.validate_config_schema(
            {
                "datadir": str(tmp_path),
                "target": {"target_name": "KRAS"},
            },
            plugin_schema_paths={},
        )


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
    assert cfg.resolve(config, "parameters.genome.assembly") == "GRCh38"
    assert cfg.resolve(config, "parameters.genome.release") == 114


def test_resolve_missing_key(sample_config):
    config = cfg.load(sample_config)
    with pytest.raises(KeyError, match="parameters.genome.nonexistent"):
        cfg.resolve(config, "parameters.genome.nonexistent")


def test_apply_overrides(sample_config):
    config = cfg.load(sample_config)
    cfg.apply_overrides(config, {"parameters.genome.release": 115})
    assert config["parameters"]["genome"]["release"] == 115


def test_apply_overrides_new_key(sample_config):
    config = cfg.load(sample_config)
    cfg.apply_overrides(config, {"parameters.genome.new_key": "value"})
    assert config["parameters"]["genome"]["new_key"] == "value"


def test_apply_overrides_rejects_scalar_parent(sample_config):
    config = cfg.load(sample_config)

    with pytest.raises(ValueError, match="cannot descend.*assembly"):
        cfg.apply_overrides(
            config,
            {"parameters.genome.assembly.version": 2},
        )


def test_schema_validation_is_separate_from_loading(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "datadir: ./data\n" "parameters:\n" "  genome:\n" "    source: ''\n"
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


def test_config_schema_accepts_other_modalities_with_their_own_design_fields(tmp_path):
    cfg.validate_config_schema(
        {
            "datadir": str(tmp_path),
            "parameters": {
                "antisense": {
                    "modality": {
                        "type": "sirna",
                        "mechanism": "risc",
                        "design": {"type": "custom", "sense_length": 21},
                    },
                }
            },
        }
    )


@pytest.mark.parametrize(
    ("antisense", "message"),
    [
        ({"modality": "aso"}, r"modality.*object"),
        (
            {"modality": {"type": "aso"}, "mechanism": "rnase-h1"},
            r"antisense.*mechanism.*unexpected",
        ),
        (
            {"modality": {"type": "aso"}, "design": {"type": "unmodified"}},
            r"antisense.*design.*unexpected",
        ),
        (
            {"modality": {"design": {"type": "unmodified"}}},
            r"modality.*type.*required",
        ),
    ],
)
def test_config_schema_requires_the_nested_modality_layout(antisense, message):
    with pytest.raises(ValueError, match=message):
        cfg.validate_config_schema(
            {"datadir": ".", "parameters": {"antisense": antisense}}
        )


@pytest.mark.parametrize("modality", ["aso", "sirna"])
def test_gapmer_design_rules_apply_only_to_aso(modality):
    config = {
        "datadir": ".",
        "parameters": {
            "antisense": {
                "modality": {"type": modality, "design": {"type": "gapmer"}}
            }
        },
    }

    if modality == "aso":
        with pytest.raises(ValueError, match="gapmer design requires"):
            cfg.validate_config_schema(config)
    else:
        cfg.validate_config_schema(config)


@pytest.mark.parametrize(
    "design",
    [
        {"type": "custom"},
        {"type": "unmodified", "sense_length": 21},
    ],
)
def test_config_schema_rejects_designs_outside_the_aso_contract(design):
    with pytest.raises(ValueError, match=r"modality.design"):
        cfg.validate_config_schema(
            {
                "datadir": ".",
                "parameters": {
                    "antisense": {"modality": {"type": "aso", "design": design}}
                },
            }
        )


def test_selected_step_rejects_an_unsupported_design(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "parameters": {
            "genome": {
                "assembly": "GRCh38",
                "release": 114,
                "source": "ensembl",
                "species": "Homo_sapiens",
            },
            "target": {"target_id": "ENSG1", "k": 16, "region": "pre-mrna"},
            "antisense": {
                "modality": {
                    "type": "aso",
                    "mechanism": "rnase-h1",
                    "design": {"type": "custom"},
                },
            },
        },
    }

    with pytest.raises(
        ValueError,
        match=r"antisense.modality.design.type.*unmodified.*gapmer",
    ):
        cfg.validate_step_config(
            config,
            [GenerateTherapeuticCandidatesStep()],
        )


def test_selected_step_accepts_an_unmodified_aso_design(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "parameters": {
            "genome": {
                "assembly": "GRCh38",
                "release": 114,
                "source": "ensembl",
                "species": "Homo_sapiens",
            },
            "target": {"target_id": "ENSG1", "k": 16, "region": "pre-mrna"},
            "antisense": {
                "modality": {
                    "type": "aso",
                    "mechanism": "rnase-h1",
                    "design": {"type": "unmodified"},
                },
            },
        },
    }

    cfg.validate_config_schema(config)
    cfg.validate_step_config(
        config,
        [GenerateTherapeuticCandidatesStep()],
    )


def test_therapeutic_step_reports_sirna_not_implemented(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "parameters": {
            "genome": {"assembly": "GRCh38"},
            "target": {"target_id": "ENSG1", "k": 16, "region": "pre-mrna"},
            "antisense": {
                "modality": {
                    "type": "sirna",
                    "mechanism": "rnase-h1",
                    "design": {"type": "unmodified"},
                },
            },
        },
    }

    with pytest.raises(
        ValueError,
        match=r"siRNA candidate generation is not implemented",
    ):
        cfg.validate_step_config(config, [GenerateTherapeuticCandidatesStep()])


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
            {"compute-intrinsic-features": IntrinsicFeaturesStep()},
        )

    message = str(raised.value)
    assert "$.steps.misspelled-step" in message
    assert "$.resources.another-misspelled-step" in message


def test_configured_input_name_must_be_declared_by_step(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "steps": {
            "compute-intrinsic-features": {
                "inputs": {"misspelled_input": {"path": "x"}},
            },
        },
    }

    with pytest.raises(ValueError, match="misspelled_input"):
        cfg.validate_configured_step_names(
            config,
            {"compute-intrinsic-features": IntrinsicFeaturesStep()},
        )


@pytest.mark.parametrize(
    "input_configuration",
    [
        {},
        {"parameters": {}},
        {"path_override": "target.json"},
        {"path": "target.json", "from": "run.gene.target_gene"},
        {
            "path": "target.json",
            "parameters": {"region": "pre-mrna"},
        },
    ],
)
def test_config_schema_rejects_invalid_step_input_configuration(
    tmp_path,
    input_configuration,
):
    with pytest.raises(ValueError, match="compute-intrinsic-features.*target_gene"):
        cfg.validate_config_schema(
            {
                "datadir": str(tmp_path),
                "steps": {
                    "compute-intrinsic-features": {
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
    assert "$.parameters.genome.assembly" in message
    assert "$.parameters.genome.release" in message
    assert "$.parameters.genome.species" in message
    assert "$.parameters.genome.source" not in message


def test_config_schema_reports_all_errors(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "parameters": {
            "genome": {
                "assembly": "",
                "release": 0,
                "species": "Homo_sapiens",
            }
        },
    }

    with pytest.raises(ValueError) as raised:
        cfg.validate_config_schema(config)

    message = str(raised.value)
    assert "$.parameters.genome.assembly" in message
    assert "$.parameters.genome.release" in message


def test_config_schema_rejects_old_genome_field_names(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "parameters": {
            "genome": {
                "assembly_id": "GRCh38",
                "ensembl_release": 114,
            }
        },
    }

    with pytest.raises(ValueError) as raised:
        cfg.validate_config_schema(config)

    message = str(raised.value)
    assert "assembly_id" in message
    assert "ensembl_release" in message


def test_config_schema_requires_one_target_identifier(
    tmp_path,
):
    config = {
        "datadir": str(tmp_path),
        "parameters": {
            "genome": {
                "assembly": "GRCh38",
                "release": 114,
                "species": "Homo_sapiens",
            },
            "target": {"k": 16, "region": "pre-mrna"},
        },
    }

    with pytest.raises(
        ValueError,
        match=r"exactly one.*target_id, target_name",
    ):
        cfg.validate_config_schema(config)


def test_config_schema_rejects_two_target_identifiers(tmp_path):
    with pytest.raises(
        ValueError,
        match=r"exactly one.*target_id, target_name",
    ):
        cfg.validate_config_schema(
            {
                "datadir": str(tmp_path),
                "parameters": {"target": {"target_id": "ENSG1", "target_name": "KRAS"}},
            }
        )


@pytest.mark.parametrize(
    "field",
    ["left_wing_length", "gap_length", "right_wing_length"],
)
@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "3"])
def test_config_schema_rejects_invalid_gapmer_segment_lengths(field, value):
    with pytest.raises(ValueError, match=rf"antisense.modality.design.{field}"):
        cfg.validate_config_schema(
            {
                "datadir": ".",
                "parameters": {
                    "antisense": {
                        "modality": {
                            "type": "aso",
                            "design": {
                                "type": "gapmer",
                                "left_wing_length": 3,
                                "gap_length": 10,
                                "right_wing_length": 3,
                                field: value,
                            },
                        },
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

    with pytest.raises(ValueError, match=rf"antisense.modality.design.*{missing_field}"):
        cfg.validate_config_schema(
            {
                "datadir": ".",
                "parameters": {
                    "antisense": {"modality": {"type": "aso", "design": design}}
                },
            }
        )


def test_config_schema_rejects_gapmer_lengths_for_unmodified_aso():
    with pytest.raises(ValueError, match="antisense.modality.design"):
        cfg.validate_config_schema(
            {
                "datadir": ".",
                "parameters": {
                    "antisense": {
                        "modality": {
                            "type": "aso",
                            "design": {"type": "unmodified", "gap_length": 10},
                        }
                    }
                },
            }
        )


def test_selected_step_requires_gapmer_segments_to_match_target_length(
    tmp_path,
):
    config = {
        "datadir": str(tmp_path),
        "parameters": {
            "genome": {"assembly": "GRCh38"},
            "target": {"target_id": "ENSG1", "k": 18, "region": "pre-mrna"},
            "antisense": {
                "modality": {
                    "type": "aso",
                    "mechanism": "rnase-h1",
                    "design": {
                        "type": "gapmer",
                        "left_wing_length": 3,
                        "gap_length": 10,
                        "right_wing_length": 3,
                    },
                },
            },
        },
    }

    cfg.validate_config_schema(config)
    with pytest.raises(
        ValueError,
        match=r"generate-therapeutic-candidates.*target-site length \(18\)",
    ):
        cfg.validate_step_config(
            config,
            [GenerateTherapeuticCandidatesStep()],
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
        "steps": {
            "generate-therapeutic-candidates": {
                "inputs": {"target_gene": {"path": str(override)}}
            }
        },
        "parameters": {
            "genome": {"assembly": "GRCh38"},
            "target": {"target_id": "ENSG1", "k": 16, "region": "pre-mrna"},
            "antisense": {
                "modality": {
                    "type": "aso",
                    "mechanism": "rnase-h1",
                    "design": {
                        "type": "gapmer",
                        "left_wing_length": 3,
                        "gap_length": 10,
                        "right_wing_length": 3,
                    },
                },
            },
        },
    }

    with pytest.raises(ValueError, match=message):
        cfg.validate_step_config(
            config,
            [GenerateTherapeuticCandidatesStep()],
        )


def test_validate_step_config_checks_override_file_contents(tmp_path):
    override = tmp_path / "target.json"
    override.write_text("{not-json")
    config = {
        "datadir": str(tmp_path),
        "steps": {
            "generate-therapeutic-candidates": {
                "inputs": {"target_gene": {"path": str(override)}}
            }
        },
        "parameters": {
            "genome": {"assembly": "GRCh38"},
            "target": {"target_id": "ENSG1", "k": 16, "region": "pre-mrna"},
            "antisense": {
                "modality": {
                    "type": "aso",
                    "mechanism": "rnase-h1",
                    "design": {
                        "type": "gapmer",
                        "left_wing_length": 3,
                        "gap_length": 10,
                        "right_wing_length": 3,
                    },
                },
            },
        },
    }

    with pytest.raises(ValueError, match="Invalid JSON"):
        cfg.validate_step_config(
            config,
            [GenerateTherapeuticCandidatesStep()],
        )


def test_config_schema_rejects_removed_input_parameter_overrides(tmp_path):
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

    with pytest.raises(ValueError, match="parameters"):
        cfg.validate_config_schema(config)


def test_validate_step_config_rejects_datadir_file(tmp_path):
    datadir = tmp_path / "data"
    datadir.touch()

    with pytest.raises(ValueError, match="datadir.*not a directory"):
        cfg.validate_step_config(
            {
                "datadir": str(datadir),
                "parameters": {
                    "genome": {
                        "assembly": "GRCh38",
                        "release": 114,
                        "species": "Homo_sapiens",
                    }
                },
            },
            [DownloadGenomeStep()],
        )


def test_step_resources_returns_supported_fields():
    step = IntrinsicFeaturesStep()
    config = {
        "resources": {
            step.name: {
                "n_workers": 4,
                "memory_mb": 8192,
            }
        }
    }

    assert cfg.step_resources(config, step) == {
        "n_workers": 4,
        "memory_mb": 8192,
    }


def test_step_resources_uses_builtin_defaults_without_configuration():
    analysis = IntrinsicFeaturesStep()
    download = DownloadGenomeStep()

    assert cfg.step_resources({}, analysis) == {
        "n_workers": 1,
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
                "n_workers": 2,
                "memory_mb": 2048,
            },
            analysis.name: {"n_workers": 8},
        }
    }

    assert cfg.step_resources(config, analysis) == {
        "n_workers": 8,
        "memory_mb": 2048,
    }
    assert cfg.step_resources(config, download) == {
        "memory_mb": 2048,
    }


def test_selected_step_rejects_unsupported_worker_setting(
    sample_config,
):
    config = cfg.load(sample_config)
    config["resources"] = {
        "download-genome": {"n_workers": 2},
    }
    cfg.validate_config_schema(config)

    with pytest.raises(
        ValueError,
        match=r"resources.download-genome.n_workers.*does not support",
    ):
        cfg.validate_step_config(config, [DownloadGenomeStep()])


def test_default_worker_setting_is_only_applied_to_supported_steps(
    sample_config,
):
    config = cfg.load(sample_config)
    config["resources"] = {
        "default": {"n_workers": 4},
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


@pytest.mark.parametrize("key", ["n_workers", "memory_mb"])
@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "4"])
def test_config_schema_rejects_invalid_resource_values(key, value):
    config = {
        "datadir": ".",
        "resources": {"analysis": {key: value}},
    }

    with pytest.raises(ValueError, match=rf"resources.analysis.{key}"):
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


@pytest.mark.parametrize(
    "features",
    ["all", "GC_content", " GC_content , CpG_count ",
     "GC_content,AT_content,T_count,CpG_count,T_content,CpG_content"],
)
def test_intrinsic_feature_schema_accepts_supported_selections(features):
    cfg.validate_config_schema(
        {"datadir": ".", "parameters": {"analysis": {"intrinsic_features": {"features": features}}}},
        plugin_schema_paths={},
    )
    IntrinsicFeaturesStep().resolved_parameter_values({}, {"features": features})


@pytest.mark.parametrize(
    "features",
    ["", " ", "all\n", "GC_contnet", "GC_content,", ",GC_content",
     "all,GC_content", "GC_content,GC_content",
     "GC_content, T_count, GC_content", "T_count,CpG_count,CpG_count", 1],
)
def test_intrinsic_feature_schema_rejects_invalid_selections(features):
    with pytest.raises(ValueError, match="intrinsic_features.features"):
        cfg.validate_config_schema(
            {"datadir": ".", "parameters": {"analysis": {"intrinsic_features": {"features": features}}}},
            plugin_schema_paths={},
        )
    with pytest.raises(ValueError, match="intrinsic_features.features"):
        IntrinsicFeaturesStep().resolved_parameter_values({}, {"features": features})


@pytest.mark.parametrize("parameters", [
    {"target.region": "exonic"}, {"target": {"region": "exonic"}},
])
def test_schema_accepts_scoped_parameters_for_steps_tasks_and_children(parameters):
    cfg.validate_config_schema({"datadir": ".", "runs": [
        {"step": "create-target-gene", "parameters": parameters},
        {"task": "instantiate-target-gene", "parameters": parameters,
         "runs": [{"id": "gene", "parameters": parameters}]},
    ]}, plugin_schema_paths={})


@pytest.mark.parametrize("parameters", [
    {"target": {"region": ["exonic"]}}, {"target": {}}, {"target": {1: "exonic"}},
])
def test_schema_rejects_invalid_nested_run_parameter_values(parameters):
    with pytest.raises(ValueError, match="runs"):
        cfg.validate_config_schema({"datadir": ".", "runs": [
            {"step": "create-target-gene", "parameters": parameters},
        ]}, plugin_schema_paths={})


def test_schema_errors_include_generated_run_names_without_mutating_config():
    config = {"datadir": ".", "runs": [
        {"step": "create-target-gene"},
        {"step": "create-target-gene", "parameters": {"target": {"region": ["exonic"]}}},
        {"step": "create-target-gene", "parameters": {"target": {"region": ["transcriptomic"]}}},
    ]}
    with pytest.raises(ValueError) as raised:
        cfg.validate_config_schema(config, plugin_schema_paths={})

    message = str(raised.value)
    assert "$.runs.create-target-gene-2.parameters.target.region" in message
    assert "$.runs.create-target-gene-3.parameters.target.region" in message
    assert all("id" not in run for run in config["runs"])


def test_schema_error_run_names_reserve_explicit_ids_declared_later():
    config = {"datadir": ".", "runs": [
        {"step": "create-target-gene", "parameters": {"target.region": []}},
        {"step": "create-target-gene", "id": "create-target-gene"},
        {"step": "create-target-gene", "id": "create-target-gene-2"},
    ]}
    with pytest.raises(ValueError, match=r"runs\.create-target-gene-3\.parameters"):
        cfg.validate_config_schema(config, plugin_schema_paths={})


def test_schema_errors_include_task_child_run_names():
    config = {"datadir": ".", "runs": [{
        "task": "instantiate-target-gene", "id": "comparison",
        "runs": [{"id": "gene", "parameters": {"target": {"region": []}}}],
    }]}
    with pytest.raises(ValueError) as raised:
        cfg.validate_config_schema(config, plugin_schema_paths={})

    assert "$.runs.comparison.runs.gene.parameters.target.region" in str(raised.value)


@pytest.mark.parametrize("runs", [
    None, [None], [{"id": []}], [{"step": []}],
    [None, {"step": "create-target-gene", "id": []}],
])
def test_malformed_run_declarations_still_report_schema_errors(runs):
    with pytest.raises(ValueError, match="runs"):
        cfg.validate_config_schema({"datadir": ".", "runs": runs}, plugin_schema_paths={})


def test_plugin_schema_errors_include_run_names(tmp_path):
    schema_path = tmp_path / "config.schema.yaml"
    schema_path.write_text(
        "type: object\n"
        "properties:\n"
        "  runs:\n"
        "    type: array\n"
        "    items:\n"
        "      properties:\n"
        "        parameters:\n"
        "          additionalProperties: {type: string}\n"
    )
    with pytest.raises(ValueError) as raised:
        cfg.validate_config_schema({"datadir": ".", "runs": [{
            "step": "example-step", "parameters": {"count": 3},
        }]}, plugin_schema_paths={"example": schema_path})

    message = str(raised.value)
    assert "Plugin 'example' schema" in message
    assert "$.runs.example-step.parameters.count" in message
