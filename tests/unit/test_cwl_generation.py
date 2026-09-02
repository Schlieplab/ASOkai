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
from pathlib import Path

import pytest
import yaml

from ASOkai._cwl.generation import GeneratedCwlBundle, generate_cwl_bundle
from ASOkai.Plugins import (
    FileInput,
    FileOutput,
    ScalarParam,
    Step,
    StepSpec,
)
from ASOkai._pipeline.catalog import get_steps
from ASOkai._pipeline.contracts.execution import (
    ExecutionPlan,
    StepInputBinding,
    StepRun,
)
from ASOkai._pipeline.contracts.paths import (
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.plan import build_plan
from ASOkai._pipeline.steps.analysis.intrinsic_features import (
    IntrinsicFeaturesStep,
)
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep


class _SpecStep(Step):
    name = "test-step"
    description = "Test step."
    spec = StepSpec()

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
    return _generate_bundle(steps, config).run_cwl


def _step_runs(steps: list[Step], config: dict) -> list[StepRun]:
    """Build main runs for focused CWL generator tests."""
    runs: list[StepRun] = []
    for step in steps:
        bindings = []
        for file_input in step.spec.inputs:
            producer_run = next(
                (
                    candidate
                    for candidate in runs
                    if candidate.step.name == file_input.source.producer
                ),
                None,
            )
            source = (
                producer_run.output(file_input.source)
                if producer_run is not None
                else Path(config["datadir"]) / "external" / file_input.name
            )
            bindings.append(StepInputBinding(file_input, source))
        runs.append(
            StepRun(
                run_id=step.name,
                step=step,
                config=config,
                inputs=tuple(bindings),
            )
        )
    return runs


def _generate_bundle(steps: list[Step], config: dict):
    return generate_cwl_bundle(_step_runs(steps, config))


def _configured_run_bundle(tmp_path: Path) -> GeneratedCwlBundle:
    """Generate two differently configured runs of one step class."""
    step = _spec_step(
        "producer",
        StepSpec(
            params=[ScalarParam("mode", str, config="producer.mode")],
            outputs=[
                FileOutput(
                    "result",
                    destination=OutputPathTemplate(
                        "{mode}/result.txt",
                        fields={"mode": TemplateField("producer.mode")},
                    ),
                )
            ],
        ),
    )
    main_run = StepRun(
        run_id="producer",
        step=step,
        config={
            "datadir": str(tmp_path),
            "producer": {"mode": "main"},
        },
    )
    configured_run = StepRun(
        run_id="consumer.producer",
        step=step,
        config={
            "datadir": str(tmp_path),
            "producer": {"mode": "configured"},
        },
    )
    return generate_cwl_bundle([main_run, configured_run])


def _shared_producer_plan(
    tmp_path: Path,
    *,
    producer_output_exists: bool = False,
) -> ExecutionPlan:
    """Plan two consumers requesting the same configured producer run."""
    producer_output = FileOutput(
        "result",
        destination=OutputPathTemplate(
            "{mode}/result.txt",
            fields={"mode": TemplateField("producer.mode")},
        ),
    )
    producer = _spec_step(
        "producer",
        StepSpec(
            params=[ScalarParam("mode", str, config="producer.mode")],
            outputs=[producer_output],
        ),
    )
    consumers = [
        _spec_step(
            name,
            StepSpec(
                inputs=[
                    FileInput(
                        "result",
                        source=producer_output,
                        configurable_parameters=("mode",),
                    ),
                ],
                outputs=[FileOutput(f"{name}_result", destination=f"{name}.txt")],
            ),
        )
        for name in ("first", "second")
    ]
    config = {
        "datadir": str(tmp_path),
        "producer": {"mode": "main"},
        "steps": {
            consumer.name: {
                "inputs": {
                    "result": {"parameters": {"mode": "alternate"}},
                },
            }
            for consumer in consumers
        },
    }
    producer_path = tmp_path / "alternate" / "result.txt"
    if producer_output_exists:
        producer_path.parent.mkdir()
        producer_path.touch()

    return build_plan(
        consumers,
        config,
        _registry={step.name: step for step in (producer, *consumers)},
    )


def _validate_bundle_with_cwltool(
    generated: GeneratedCwlBundle,
    directory: Path,
) -> None:
    """Write and validate one complete generated bundle."""
    executable = shutil.which("cwltool")
    if executable is None:
        pytest.skip("cwltool is not installed")
    assert executable is not None

    steps_dir = directory / "steps"
    steps_dir.mkdir()
    for filename, contents in generated.step_cwls.items():
        (steps_dir / filename).write_text(contents)
    run_path = directory / "run.cwl"
    run_path.write_text(generated.run_cwl)
    (directory / "publish.cwl").write_text(generated.publish_cwl)
    (directory / "output-layout.yml").write_text(generated.output_layout)

    result = subprocess.run(
        [executable, "--validate", str(run_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


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
            "k": 16,
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
    assert "download-genome.dna_output" not in doc["inputs"]


def test_generate_cwl_uses_declared_step_input_types(workflow_config):
    doc = yaml.safe_load(
        _generate_run_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            workflow_config,
        )
    )

    assert doc["inputs"]["download-genome.release"] == "int"
    assert doc["inputs"]["create-target-gene.k"] == "int"
    assert doc["inputs"]["create-target-gene.region"]["type"]["type"] == "enum"


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

    create_inputs = doc["steps"]["step_create_target_gene"]["in"]
    for name in ("dna", "cdna", "annotation", "db"):
        workflow_input = f"create-target-gene.{name}"
        assert doc["inputs"][workflow_input] == "File"
        assert create_inputs[name] == workflow_input


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
    generated = _generate_bundle(
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
        "id": "download-genome.dna",
        "destination": (
            "GRCh38/genomes/ensembl/114/"
            "Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz"
        ),
    }
    assert set(generated.step_cwls) == {
        "download-genome.cwl",
        "create-target-gene.cwl",
    }


def test_generate_cwl_publishes_a_root_file_as_a_file(tmp_path):
    step = _spec_step(
        "single-file",
        StepSpec(outputs=[FileOutput("result", destination="result.txt")]),
    )

    generated = _generate_bundle([step], {"datadir": str(tmp_path)})
    workflow = yaml.safe_load(generated.run_cwl)
    publisher = yaml.safe_load(generated.publish_cwl)

    assert workflow["outputs"]["published_result_txt"] == {
        "type": "File",
        "outputSource": "publish_outputs/published_result_txt",
    }
    assert publisher["outputs"]["published_result_txt"] == {
        "type": "File",
        "outputBinding": {"glob": "published/result.txt"},
    }


def test_generate_cwl_keeps_single_process_steps_at_one_core(workflow_config):
    workflow_config["resources"] = {
        "download-genome": {"memory_mb": 8192},
        "create-target-gene": {"memory_mb": 16384},
    }

    generated = _generate_bundle(
        [DownloadGenomeStep(), CreateTargetGeneStep()],
        workflow_config,
    )
    download = yaml.safe_load(generated.step_cwls["download-genome.cwl"])
    create = yaml.safe_load(generated.step_cwls["create-target-gene.cwl"])
    workflow = yaml.safe_load(generated.run_cwl)

    assert download["requirements"]["ResourceRequirement"] == {
        "coresMin": 1,
        "ramMin": 8192,
    }
    assert create["requirements"]["ResourceRequirement"] == {
        "coresMin": 1,
        "ramMin": 16384,
    }
    assert "n_processes" not in download["inputs"]
    assert "n_processes" not in create["inputs"]
    assert "n_processes" not in workflow["steps"]["step_download_genome"]["in"]
    assert "n_processes" not in workflow["steps"]["step_create_target_gene"]["in"]


def test_generate_cwl_configures_processes_for_analysis_steps(workflow_config):
    workflow_config["resources"] = {
        "intrinsic-features": {"n_processes": 4, "memory_mb": 8192},
    }

    generated = _generate_bundle(
        [IntrinsicFeaturesStep()],
        workflow_config,
    )
    intrinsic = yaml.safe_load(
        generated.step_cwls["intrinsic-features.cwl"]
    )
    workflow = yaml.safe_load(generated.run_cwl)

    assert intrinsic["requirements"]["ResourceRequirement"] == {
        "coresMin": 4,
        "ramMin": 8192,
    }
    assert intrinsic["inputs"]["n_processes"] == {
        "type": "int",
        "doc": "Number of parallel workers allocated to this step.",
        "default": 1,
        "inputBinding": {"prefix": "--n-processes"},
    }
    assert workflow["steps"]["step_intrinsic_features"]["in"]["n_processes"] == {
        "default": 4,
    }
    assert "n_processes" not in workflow["inputs"]


def test_generate_cwl_uses_default_resource_requirement_when_not_configured(
    workflow_config,
):
    generated = _generate_bundle(
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

    generated = _generate_bundle([step], workflow_config)
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
        StepRun(step.name, step, {}).cwl_spec()
    with pytest.raises(ValueError, match="reserved.*n_processes"):
        step.build_parser()


def test_generate_cwl_references_generated_step_files(workflow_config):
    doc = yaml.safe_load(
        _generate_run_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            workflow_config,
        )
    )

    assert doc["steps"]["step_download_genome"]["run"] == "steps/download-genome.cwl"
    assert doc["steps"]["step_create_target_gene"]["run"] == "steps/create-target-gene.cwl"


def test_generate_cwl_namespaces_each_concrete_run(tmp_path):
    generated = _configured_run_bundle(tmp_path)
    document = yaml.safe_load(generated.run_cwl)
    layout = yaml.safe_load(generated.output_layout)

    assert set(generated.step_cwls) == {
        "producer.cwl",
        "consumer.producer.cwl",
    }
    assert document["inputs"] == {
        "producer.mode": "string",
        "consumer.producer.mode": "string",
    }
    assert document["steps"]["step_producer"] == {
        "run": "steps/producer.cwl",
        "in": {"mode": "producer.mode"},
        "out": ["result"],
    }
    assert document["steps"]["step_consumer.producer"] == {
        "run": "steps/consumer.producer.cwl",
        "in": {"mode": "consumer.producer.mode"},
        "out": ["result"],
    }
    assert [entry["id"] for entry in layout["outputs"]] == [
        "producer.result",
        "consumer.producer.result",
    ]


def test_shared_producer_is_generated_and_wired_once(tmp_path):
    plan = _shared_producer_plan(tmp_path)

    generated = generate_cwl_bundle(list(plan.runs_to_execute))
    workflow = yaml.safe_load(generated.run_cwl)
    layout = yaml.safe_load(generated.output_layout)

    assert set(generated.step_cwls) == {
        "first.producer.cwl",
        "first.cwl",
        "second.cwl",
    }
    assert set(workflow["steps"]) == {
        "step_first.producer",
        "step_first",
        "step_second",
        "publish_outputs",
    }
    assert workflow["steps"]["step_first"]["in"]["result"] == (
        "step_first.producer/result"
    )
    assert workflow["steps"]["step_second"]["in"]["result"] == (
        "step_first.producer/result"
    )
    publication_sources = workflow["steps"]["publish_outputs"]["in"]["files"][
        "source"
    ]
    assert publication_sources.count("step_first.producer/result") == 1
    assert [entry["id"] for entry in layout["outputs"]] == [
        "first.producer.result",
        "first.first_result",
        "second.second_result",
    ]


def test_reused_shared_producer_is_one_workflow_input(tmp_path):
    plan = _shared_producer_plan(
        tmp_path,
        producer_output_exists=True,
    )

    generated = generate_cwl_bundle(list(plan.runs_to_execute))
    workflow = yaml.safe_load(generated.run_cwl)

    assert set(generated.step_cwls) == {"first.cwl", "second.cwl"}
    assert "step_first.producer" not in workflow["steps"]
    assert workflow["inputs"] == {"first.producer.result": "File"}
    assert workflow["steps"]["step_first"]["in"]["result"] == (
        "first.producer.result"
    )
    assert workflow["steps"]["step_second"]["in"]["result"] == (
        "first.producer.result"
    )


def test_registered_step_specs_cover_config_and_output_keys(workflow_config):
    runs = _step_runs(list(get_steps().values()), workflow_config)
    for run in runs:
        step = run.step
        input_names = run.cwl_spec().input_names()
        output_names = run.cwl_spec().output_names()

        assert set(step.config_map).issubset(input_names)
        assert {item.name for item in step.spec.inputs}.issubset(input_names)
        assert set(run.output_paths()) == output_names


def test_generate_cwl_qualifies_same_named_inputs_by_run(tmp_path):
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

    document = yaml.safe_load(
        _generate_run_cwl([first, second], {"datadir": str(tmp_path)})
    )

    assert document["inputs"]["first.shared"] == "string"
    assert document["inputs"]["second.shared"] == "int"


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


def test_generate_cwl_rejects_duplicate_planned_run_ids(tmp_path):
    first = _spec_step(
        "duplicate",
        StepSpec(outputs=[FileOutput("first", destination="first.txt")]),
    )
    second = _spec_step(
        "duplicate",
        StepSpec(outputs=[FileOutput("second", destination="second.txt")]),
    )

    with pytest.raises(ValueError, match="Duplicate planned run id"):
        _generate_run_cwl([first, second], {"datadir": str(tmp_path)})


def test_generate_cwl_rejects_distinct_source_run_with_planned_id(
    tmp_path,
):
    producer = _spec_step(
        "producer",
        StepSpec(
            params=[ScalarParam("mode", str, config="producer.mode")],
            outputs=[
                FileOutput(
                    "result",
                    destination=OutputPathTemplate(
                        "{mode}/result.txt",
                        fields={"mode": TemplateField("producer.mode")},
                    ),
                )
            ],
        ),
    )
    consumer = _spec_step(
        "consumer",
        StepSpec(
            inputs=[
                FileInput(
                    "result",
                    source=producer.spec.output("result"),
                ),
            ],
            outputs=[FileOutput("done", destination="done.txt")],
        ),
    )
    main_config = {
        "datadir": str(tmp_path),
        "producer": {"mode": "main"},
    }
    planned_producer = StepRun("producer", producer, main_config)
    referenced_producer = StepRun("producer", producer, main_config)
    consumer_run = StepRun(
        "consumer",
        consumer,
        main_config,
        inputs=(
            StepInputBinding(
                consumer.spec.input("result"),
                referenced_producer.output(producer.spec.output("result")),
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match="different StepRun object.*producer",
    ):
        generate_cwl_bundle([planned_producer, consumer_run])


def test_generate_cwl_rejects_an_empty_plan():
    with pytest.raises(ValueError, match="at least one output"):
        generate_cwl_bundle([])


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


def test_generated_registered_tools_and_workflow_validate_with_cwltool(
    workflow_config,
    tmp_path,
):
    steps = list(get_steps().values())
    generated = _generate_bundle(steps, workflow_config)
    _validate_bundle_with_cwltool(generated, tmp_path)


def test_generated_dotted_run_ids_validate_with_cwltool(tmp_path):
    generated = _configured_run_bundle(tmp_path)
    _validate_bundle_with_cwltool(generated, tmp_path)
