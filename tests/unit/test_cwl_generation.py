#!/usr/bin/env python
"""
Filename: tests/unit/test_cwl_generation.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Tests for generated top-level runtime CWLs.
License: LGPL-3.0-or-later
"""

import shutil
import subprocess

import pytest
import yaml

from ASOkai._cwl.generation import StepCwlGenerator, generate_cwl_bundle
from ASOkai.Plugins import (
    FileInput,
    FileOutput,
    ScalarParam,
    Step,
    StepSpec,
)
from ASOkai.Plugins._registry import get_steps
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep


class _SpecStep(Step):
    name = "test-step"
    description = "Test step."
    spec = StepSpec()

    def outputs_exist(self, config):
        return False

    def cleanup(self, config):
        pass


def _spec_step(
    name: str,
    spec: StepSpec,
) -> Step:
    """Return an isolated Step subclass configured with class-level metadata."""
    namespace = {
        "__module__": __name__,
        "name": name,
        "spec": spec,
    }
    namespace.update(
        {
            f"declared_output_{index}": output
            for index, output in enumerate(spec.outputs)
        }
    )
    ConfiguredSpecStep = type("ConfiguredSpecStep", (_SpecStep,), namespace)
    return ConfiguredSpecStep()


def _generate_run_cwl(
    steps: list[Step],
    config: dict,
) -> str:
    return generate_cwl_bundle(steps, config).run_cwl


@pytest.fixture
def workflow_config(tmp_path):
    return {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "GRCh38",
            "ensembl_release": 114,
            "source": "ensembl",
            "species": "Homo_sapiens",
        },
        "target": {
            "target_id": "ENSG00000133703",
            "target_name": "KRAS",
            "k": 16,
            "region": "pre-mrna",
        },
        "antisense": {
            "modality": "aso",
            "mechanism": "rnase-h1",
            "chemistry": {"type": "gapmer", "layout": "3-10-3"},
        },
    }


def test_generate_cwl_wires_download_outputs_into_create_target_gene(workflow_config):
    doc = yaml.safe_load(
        _generate_run_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            workflow_config,
        )
    )

    create_inputs = doc["steps"]["step_create_target_gene"]["in"]
    assert create_inputs["dna"] == "step_download_genome/dna"
    assert create_inputs["cdna"] == "step_download_genome/cdna"
    assert create_inputs["annotation"] == "step_download_genome/annotation"
    assert create_inputs["db"] == "step_download_genome/db"


def test_generate_cwl_does_not_expose_derived_output_filenames_as_inputs(
    workflow_config,
):
    doc = yaml.safe_load(
        _generate_run_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            workflow_config,
        )
    )

    download_inputs = doc["steps"]["step_download_genome"]["in"]
    assert "dna_output" not in download_inputs
    assert "cdna_output" not in download_inputs
    assert "annotation_output" not in download_inputs
    assert "dna_output" not in doc["inputs"]


def test_generate_cwl_uses_declared_step_input_types(workflow_config):
    doc = yaml.safe_load(
        _generate_run_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            workflow_config,
        )
    )

    assert doc["inputs"]["release"] == "int"
    assert doc["inputs"]["k"] == "int"
    assert doc["inputs"]["region"]["type"]["type"] == "enum"


def test_generate_cwl_external_dependency_outputs_are_file_inputs(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "GRCh38",
            "ensembl_release": 114,
            "source": "ensembl",
            "species": "Homo_sapiens",
        },
        "target": {
            "target_id": "ENSG00000133703",
            "target_name": "KRAS",
            "k": 16,
            "region": "pre-mrna",
        },
    }

    doc = yaml.safe_load(
        _generate_run_cwl(
            [CreateTargetGeneStep()],
            config,
        )
    )

    assert doc["inputs"]["dna"] == "File"
    assert doc["inputs"]["cdna"] == "File"
    assert doc["steps"]["step_create_target_gene"]["in"]["dna"] == "dna"
    assert doc["steps"]["step_create_target_gene"]["in"]["cdna"] == "cdna"


def test_generate_cwl_input_overrides_keep_declared_file_types_when_not_wired(workflow_config):
    doc = yaml.safe_load(_generate_run_cwl([CreateTargetGeneStep()], workflow_config))

    assert doc["inputs"]["dna"] == "File"
    assert doc["inputs"]["cdna"] == "File"
    assert doc["inputs"]["annotation"] == "File"
    assert doc["inputs"]["db"] == "File"


def test_generate_cwl_publishes_every_step_output_under_data_roots(workflow_config):
    doc = yaml.safe_load(
        _generate_run_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            workflow_config,
        )
    )

    assert set(doc["outputs"]) == {"published_GRCh38"}
    assert doc["outputs"]["published_GRCh38"] == {
        "type": "Directory",
        "outputSource": "publish_outputs/published_GRCh38",
    }
    assert doc["steps"]["publish_outputs"]["in"]["files"]["source"] == [
        "step_download_genome/dna",
        "step_download_genome/cdna",
        "step_download_genome/annotation",
        "step_download_genome/db",
        "step_create_target_gene/target_gene",
    ]
    assert doc["steps"]["publish_outputs"]["in"]["files"]["linkMerge"] == (
        "merge_flattened"
    )
    assert set(doc["steps"]).isdisjoint(doc["outputs"])


def test_generate_cwl_bundle_contains_every_required_document(workflow_config):
    generated = generate_cwl_bundle(
        [DownloadGenomeStep(), CreateTargetGeneStep()],
        workflow_config,
    )
    publisher = yaml.safe_load(generated.publish_cwl)
    layout = yaml.safe_load(generated.output_layout)

    assert publisher["baseCommand"] == ["ASOkai", "publish-outputs"]
    assert publisher["inputs"]["files"]["type"] == {
        "type": "array",
        "items": "File",
    }
    assert publisher["outputs"]["published_GRCh38"] == {
        "type": "Directory",
        "outputBinding": {"glob": "published/GRCh38"},
    }
    assert "InlineJavascriptRequirement" not in publisher.get("requirements", {})
    assert layout["outputs"][0] == {
        "id": "step_download_genome__dna",
        "destination": (
            "GRCh38/genomes/ensembl/114/"
            "Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz"
        ),
    }
    assert set(generated.step_cwls) == {
        "download-genome.cwl",
        "create-target-gene.cwl",
    }


def test_generate_cwl_adds_each_steps_configured_resources(workflow_config):
    workflow_config["resources"] = {
        "download-genome": {"n_processes": 2, "memory_mb": 4096},
        "create-target-gene": {"n_processes": 8, "memory_mb": 16384},
    }

    generated = generate_cwl_bundle(
        [DownloadGenomeStep(), CreateTargetGeneStep()],
        workflow_config,
    )
    download = yaml.safe_load(generated.step_cwls["download-genome.cwl"])
    create = yaml.safe_load(generated.step_cwls["create-target-gene.cwl"])
    workflow = yaml.safe_load(generated.run_cwl)

    assert download["requirements"]["ResourceRequirement"] == {
        "coresMin": 2,
        "ramMin": 4096,
    }
    assert create["requirements"]["ResourceRequirement"] == {
        "coresMin": 8,
        "ramMin": 16384,
    }
    assert download["inputs"]["n_processes"] == {
        "type": "int",
        "doc": "Number of processes allocated to this step.",
        "default": 1,
        "inputBinding": {"prefix": "--n-processes"},
    }
    assert create["inputs"]["n_processes"] == download["inputs"]["n_processes"]
    assert workflow["steps"]["step_download_genome"]["in"]["n_processes"] == {
        "default": 2,
    }
    assert workflow["steps"]["step_create_target_gene"]["in"]["n_processes"] == {
        "default": 8,
    }
    assert "n_processes" not in workflow["inputs"]


def test_generate_cwl_uses_default_resource_requirement_when_not_configured(
    workflow_config,
):
    generated = generate_cwl_bundle(
        [DownloadGenomeStep()],
        workflow_config,
    )
    download = yaml.safe_load(generated.step_cwls["download-genome.cwl"])

    assert download["requirements"]["ResourceRequirement"] == {
        "coresMin": 1,
        "ramMin": 4096,
    }


def test_generate_cwl_resource_precedence(workflow_config):
    step = _spec_step(
        "authored-resources",
        StepSpec(
            requirements={
                "ResourceRequirement": {
                    "coresMin": 6,
                    "ramMin": 12288,
                    "tmpdirMin": 2048,
                }
            },
            outputs=[FileOutput("result", destination="result.txt")],
        ),
    )
    workflow_config["resources"] = {
        "authored-resources": {"memory_mb": 8192},
    }

    generated = generate_cwl_bundle([step], workflow_config)
    document = yaml.safe_load(generated.step_cwls["authored-resources.cwl"])

    assert document["requirements"]["ResourceRequirement"] == {
        "coresMin": 6,
        "ramMin": 8192,
        "tmpdirMin": 2048,
    }


@pytest.mark.parametrize(
    "parameter",
    [
        ScalarParam("n_processes", int),
        ScalarParam("workers", int, prefix="--n-processes"),
    ],
)
def test_step_rejects_reserved_n_processes_parameter(parameter):
    step = _spec_step(
        "conflicting-processes",
        StepSpec(params=[parameter]),
    )

    with pytest.raises(ValueError, match="reserved.*n_processes"):
        step.cwl_spec({})
    with pytest.raises(ValueError, match="reserved.*n_processes"):
        step.build_parser()


def test_generate_cwl_normalizes_step_ids_with_underscores(workflow_config):
    doc = yaml.safe_load(
        _generate_run_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            workflow_config,
        )
    )

    assert "step_download_genome" in doc["steps"]
    assert "step_create_target_gene" in doc["steps"]


def test_generate_cwl_references_generated_step_files(workflow_config):
    doc = yaml.safe_load(
        _generate_run_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            workflow_config,
        )
    )

    assert doc["steps"]["step_download_genome"]["run"] == "steps/download-genome.cwl"
    assert doc["steps"]["step_create_target_gene"]["run"] == "steps/create-target-gene.cwl"


def test_registered_step_output_paths_define_names(workflow_config):
    for step in get_steps().values():
        assert tuple(step.output_paths(workflow_config).keys())


def test_registered_step_specs_cover_config_and_output_keys(workflow_config):
    for step in get_steps().values():
        input_names = step.cwl_spec(workflow_config).input_names()
        output_names = step.cwl_spec(workflow_config).output_names()

        assert set(step.config_map).issubset(input_names)
        assert set(step.input_overrides).issubset(input_names)
        assert set(step.output_paths(workflow_config)) == output_names


def test_generate_cwl_rejects_conflicting_shared_input_types(tmp_path):
    first = _spec_step(
        "first",
        StepSpec(
            params=[ScalarParam("shared", str, config="first.shared")],
            outputs=[
                FileOutput("first_result", destination="first_result.txt")
            ],
        ),
    )
    second = _spec_step(
        "second",
        StepSpec(
            params=[ScalarParam("shared", int, config="second.shared")],
            outputs=[
                FileOutput("second_result", destination="second_result.txt")
            ],
        ),
    )

    with pytest.raises(ValueError, match="conflicting CWL types"):
        _generate_run_cwl([first, second], {"datadir": str(tmp_path)})


def test_generate_cwl_does_not_wire_undeclared_dependency_outputs(tmp_path):
    producer = _spec_step(
        "producer",
        StepSpec(outputs=[FileOutput("unused", destination="unused.txt")]),
    )
    consumer = _spec_step(
        "consumer",
        StepSpec(outputs=[FileOutput("result", destination="result.txt")]),
    )

    doc = yaml.safe_load(
        _generate_run_cwl([producer, consumer], {"datadir": str(tmp_path)})
    )

    assert "unused" not in doc["steps"]["step_consumer"]["in"]
    assert "unused" not in doc["inputs"]


def test_generate_cwl_wires_differently_named_input_to_exact_output(tmp_path):
    producer = _spec_step(
        "producer",
        StepSpec(
            outputs=[FileOutput("result", destination="producer-result.txt")]
        ),
    )
    consumer = _spec_step(
        "consumer",
        StepSpec(
            inputs=[
                FileInput(
                    "renamed_input",
                    source=producer.spec.output("result"),
                )
            ],
            outputs=[FileOutput("done", destination="consumer-done.txt")],
        ),
    )

    doc = yaml.safe_load(
        _generate_run_cwl([producer, consumer], {"datadir": str(tmp_path)})
    )

    assert doc["steps"]["step_consumer"]["in"]["renamed_input"] == (
        "step_producer/result"
    )


def test_generate_cwl_rejects_a_same_name_output_from_another_step_class(
    tmp_path,
):
    expected_producer = _spec_step(
        "producer",
        StepSpec(outputs=[FileOutput("result", destination="expected.txt")]),
    )
    replacement_producer = _spec_step(
        "producer",
        StepSpec(outputs=[FileOutput("result", destination="replacement.txt")]),
    )
    consumer = _spec_step(
        "consumer",
        StepSpec(
            inputs=[
                FileInput(
                    "result",
                    source=expected_producer.spec.output("result"),
                )
            ],
            outputs=[FileOutput("done", destination="done.txt")],
        ),
    )

    with pytest.raises(ValueError, match="does not belong to 'producer'"):
        _generate_run_cwl(
            [replacement_producer, consumer],
            {"datadir": str(tmp_path)},
        )


def test_generate_cwl_rejects_duplicate_planned_step_names(tmp_path):
    first = _spec_step(
        "duplicate",
        StepSpec(outputs=[FileOutput("first", destination="first.txt")]),
    )
    second = _spec_step(
        "duplicate",
        StepSpec(outputs=[FileOutput("second", destination="second.txt")]),
    )

    with pytest.raises(ValueError, match="Duplicate planned step name"):
        _generate_run_cwl([first, second], {"datadir": str(tmp_path)})


def test_generate_cwl_allows_matching_work_filenames_in_separate_steps(tmp_path):
    first = _spec_step(
        "first",
        StepSpec(outputs=[FileOutput("shared", destination="first/shared.txt")]),
    )
    second = _spec_step(
        "second",
        StepSpec(outputs=[FileOutput("shared", destination="second/shared.txt")]),
    )

    _generate_run_cwl([first, second], {"datadir": str(tmp_path)})


def test_generate_cwl_rejects_matching_work_filenames_within_one_step(tmp_path):
    step = _spec_step(
        "producer",
        StepSpec(
            outputs=[
                FileOutput("first", destination="a/shared.txt"),
                FileOutput("second", destination="b/shared.txt"),
            ]
        ),
    )

    with pytest.raises(ValueError, match="Duplicate CWL output filename.*shared.txt"):
        _generate_run_cwl([step], {"datadir": str(tmp_path)})


@pytest.mark.skipif(shutil.which("cwltool") is None, reason="cwltool is not installed")
def test_generated_registered_tools_and_workflow_validate_with_cwltool(
    workflow_config,
    tmp_path,
):
    steps = list(get_steps().values())
    steps_dir = tmp_path / "steps"
    steps_dir.mkdir()
    generator = StepCwlGenerator()
    for step in steps:
        (steps_dir / f"{step.name}.cwl").write_text(
            generator.render(step, workflow_config)
        )

    generated = generate_cwl_bundle(steps, workflow_config)
    run_path = tmp_path / "run.cwl"
    run_path.write_text(generated.run_cwl)
    (tmp_path / "publish.cwl").write_text(generated.publish_cwl)
    (tmp_path / "output-layout.yml").write_text(generated.output_layout)

    result = subprocess.run(
        ["cwltool", "--validate", str(run_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
