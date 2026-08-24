#!/usr/bin/env python
"""
Filename: tests/docs/test_generated_references.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Tests for documentation generated from runtime contracts.
License: LGPL-3.0-or-later
"""

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import yaml
from docutils import nodes
from docutils.utils import new_document
from sphinx import addnodes

pytest.importorskip("sphinx")

ROOT = Path(__file__).parents[2]
sys.path.insert(
    0,
    str(ROOT / "docs/source/_extensions"),
)

from contract_docs import (  # noqa: E402
    build_runnable_list,
    build_runnable_reference,
    build_step_list,
    build_step_reference,
    collect_step_config_fields,
    collect_step_schema_rules,
    get_built_in_step,
    get_built_in_steps,
    get_built_in_runnable,
    get_built_in_runnables,
    serializable_contract_nodes,
)
from contract_docs.file_contracts import (  # noqa: E402
    append_serializable_contracts,
    json_contract_types,
    json_example,
)
from contract_docs.rendering import (  # noqa: E402
    local_contents,
    section,
)
from ASOkai._pipeline.contracts.file_types import CsvFile, JsonFile  # noqa: E402
from ASOkai._pipeline.contracts.step_spec import StepSpec  # noqa: E402
from ASOkai._pipeline.steps.analysis.base import AnalysisStep  # noqa: E402
from ASOkai._pipeline.steps.core.base import CoreStep  # noqa: E402
from ASOkai.Antisense import (  # noqa: E402
    ASO,
    AntisenseTherapeutic,
    Gapmer,
    Oligonucleotide,
    siRNA,
)
from ASOkai.Biochemistry import Chemistry  # noqa: E402
from ASOkai.Sites import Site, TranscriptSite  # noqa: E402
from ASOkai.Targets import TargetGene  # noqa: E402


def _config_schema() -> dict:
    schema_path = ROOT / "src/ASOkai/_pipeline/config.schema.yaml"
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    assert isinstance(schema, dict)
    return schema


def test_step_config_collects_nested_and_dynamic_fields() -> None:
    step = get_built_in_step("intrinsic-features")
    fields = {
        field.path: field
        for field in collect_step_config_fields(step, _config_schema())
    }

    assert fields["datadir"].requirement == "Required"
    assert fields["target.region"].constraints == (
        "one of: exonic_only, pre-mrna, transcriptomic"
    )
    assert fields["resources.intrinsic-features.n_processes"].value_type == "integer"
    assert fields["target.target_id"].requirement == (
        "Exactly one of target_id or target_name is required"
    )


def test_every_used_built_in_config_field_has_a_schema_description() -> None:
    for step in get_built_in_steps():
        for field in collect_step_config_fields(step, _config_schema()):
            assert field.description != "—", f"{step.name}: {field.path}"


def test_every_built_in_step_has_generated_documentation() -> None:
    for step in get_built_in_steps():
        assert get_built_in_step(step.name) is step
        assert build_step_reference(step, _config_schema())


def test_step_index_is_generated_from_the_built_in_registry() -> None:
    core_list = build_step_list("core", include_descriptions=True)
    analysis_list = build_step_list("analysis")
    built_in_steps = get_built_in_steps()

    for step_type, generated_list in (
        (CoreStep, core_list),
        (AnalysisStep, analysis_list),
    ):
        expected_targets = [
            f"/steps/{step.name}"
            for step in built_in_steps
            if isinstance(step, step_type)
        ]
        generated_targets = [
            link["reftarget"]
            for link in generated_list.findall(addnodes.pending_xref)
        ]
        assert generated_targets == expected_targets


@pytest.mark.parametrize("kind", ["task", "workflow"])
def test_every_built_in_runnable_has_generated_documentation(kind: str) -> None:
    for runnable in get_built_in_runnables(kind):
        assert get_built_in_runnable(kind, runnable.name) is runnable
        assert build_runnable_reference(runnable, kind)
        assert (
            ROOT / f"docs/source/{kind}s/{runnable.name}.rst"
        ).is_file()


@pytest.mark.parametrize("kind", ["task", "workflow"])
def test_runnable_indexes_are_generated_from_the_registry(kind: str) -> None:
    runnable_list = build_runnable_list(kind)
    assert [
        link["reftarget"]
        for link in runnable_list.findall(addnodes.pending_xref)
    ] == [
        f"/{kind}s/{runnable.name}"
        for runnable in get_built_in_runnables(kind)
    ]


def test_task_reference_links_to_its_steps() -> None:
    task = get_built_in_runnable("task", "instantiate-target-gene")
    generated = build_runnable_reference(
        task,
        "task",
        refdoc="tasks/instantiate-target-gene",
    )
    reference = "\n".join(node.astext() for node in generated)
    link_targets = {
        link["reftarget"]
        for node in generated
        for link in node.findall(addnodes.pending_xref)
    }

    assert "ASOkai run --tasks instantiate-target-gene" in reference
    assert "Expanded steps" not in reference
    assert "Contracts" not in reference
    assert link_targets == {
        "/steps/download-genome",
        "/steps/create-target-gene",
    }


def test_workflow_reference_links_members_and_expanded_steps() -> None:
    workflow = get_built_in_runnable("workflow", "standard")
    generated = build_runnable_reference(
        workflow,
        "workflow",
        refdoc="workflows/standard",
    )
    reference = "\n".join(node.astext() for node in generated)
    link_targets = {
        link["reftarget"]
        for node in generated
        for link in node.findall(addnodes.pending_xref)
    }

    assert "ASOkai run --workflow standard" in reference
    assert "Direct members" in reference
    assert "Expanded steps" in reference
    assert "Contracts" not in reference
    assert link_targets == {
        "/tasks/instantiate-target-gene",
        "/steps/download-genome",
        "/steps/create-target-gene",
        "/steps/generate-antisense-candidates",
        "/steps/intrinsic-features",
    }


def test_step_config_contains_only_fields_used_by_that_step() -> None:
    step = get_built_in_step("intrinsic-features")
    fields = {
        field.path: field
        for field in collect_step_config_fields(step, _config_schema())
    }

    assert fields["datadir"].requirement == "Required"
    assert fields["target.k"].requirement == "Required"
    assert fields[
        "steps.intrinsic-features.inputs.target_gene.path_override"
    ].requirement == "Optional path override"
    assert fields["resources.intrinsic-features.n_processes"].requirement == (
        "Overrides resources.default"
    )
    assert fields["resources.default.n_processes"].requirement == (
        "Built-in fallback: 1"
    )
    assert "antisense.design.gap_length" not in fields
    assert collect_step_schema_rules(step, _config_schema()) == [
        "exactly one of these config values is required: "
        "target.target_id, target.target_name"
    ]


def test_single_process_step_omits_process_count() -> None:
    step = get_built_in_step("download-genome")
    fields = {
        field.path
        for field in collect_step_config_fields(step, _config_schema())
    }
    reference = "\n".join(
        node.astext()
        for node in build_step_reference(step, _config_schema())
    )

    assert "resources.default.n_processes" not in fields
    assert "resources.download-genome.n_processes" not in fields
    assert "n_processes" not in reference
    assert "resources.default.memory_mb" in reference
    assert "resources.download-genome.memory_mb" in reference


def test_step_reference_renders_declared_dependencies_and_file_ports() -> None:
    step = get_built_in_step("intrinsic-features")
    generated_nodes = build_step_reference(
        step,
        _config_schema(),
        refdoc="steps/intrinsic-features",
    )
    reference = "\n".join(node.astext() for node in generated_nodes)

    assert "create-target-gene.target_gene" in reference
    input_path = (
        "steps.intrinsic-features.inputs.target_gene.path_override"
    )
    assert input_path in reference
    assert "{target}_k{k}_{region}_intrinsic.csv" in reference
    assert f"unless {input_path} is configured" in reference
    assert (
        "GRCh38/targets/ENSG00000133703/analysis/intrinsic/"
        "ENSG00000133703_k16_pre-mrna_intrinsic.csv" in reference
    )

    links = [
        descendant
        for node in generated_nodes
        for descendant in node.findall(addnodes.pending_xref)
    ]
    assert any(
        link["refdoc"] == "steps/intrinsic-features"
        and link["reftarget"] == "/steps/create-target-gene"
        for link in links
    )
    assert any(link["reftarget"] == "ASOkai.Targets.TargetGene" for link in links)
    assert not any("file-contracts" in link["reftarget"] for link in links)

    table_classes = {
        css_class
        for node in generated_nodes
        for generated_table in node.findall(nodes.table)
        for css_class in generated_table["classes"]
    }
    assert "asokai-step-scalar-outputs" in table_classes
    assert "asokai-step-file-outputs" in table_classes
    assert "asokai-step-resources" in table_classes
    assert "asokai-step-applicability" not in table_classes
    assert "asokai-analysis-output-columns" in table_classes
    assert "Step override" in reference
    assert "Shared default" in reference
    assert "Built-in fallback" in reference
    assert "JSON — TargetGene" in reference
    assert "CSV" in reference
    assert "Output columns" in reference
    assert "first row is a header" in reference
    assert "Rows: Intrinsic features per target site" in reference
    assert "Applicability" not in reference
    assert not any(
        isinstance(node, nodes.section) and node[0].astext() == "File contracts"
        for node in generated_nodes
    )


def test_step_reference_renders_only_declared_applicability() -> None:
    class RestrictedStep(CoreStep):
        name = "restricted-example"
        description = "Example step with an explicit biological restriction."
        spec = StepSpec(
            compatible_with={
                "antisense.mechanism": ["rnase-h1"],
            }
        )

    step = RestrictedStep()
    generated_nodes = build_step_reference(step, _config_schema())
    reference = "\n".join(node.astext() for node in generated_nodes)
    table_classes = {
        css_class
        for node in generated_nodes
        for generated_table in node.findall(nodes.table)
        for css_class in generated_table["classes"]
    }

    assert "asokai-step-applicability" in table_classes
    assert "antisense.mechanism" in reference
    assert "rnase-h1" in reference


def test_candidate_generation_has_no_assumed_applicability() -> None:
    step = get_built_in_step("generate-antisense-candidates")
    generated_nodes = build_step_reference(step, _config_schema())
    reference = "\n".join(node.astext() for node in generated_nodes)

    assert step.spec.compatible_with == {}
    assert "Applicability" not in reference


def test_candidate_generation_documents_conditional_design_fields() -> None:
    step = get_built_in_step("generate-antisense-candidates")
    fields = {
        field.path: field
        for field in collect_step_config_fields(step, _config_schema())
    }
    rules = collect_step_schema_rules(step, _config_schema())

    assert fields["antisense.design.type"].requirement == "Required"
    for field_name in (
        "left_wing_length",
        "gap_length",
        "right_wing_length",
    ):
        field = fields[f"antisense.design.{field_name}"]
        assert field.requirement == "Optional"
        assert "Required for a gapmer design" in field.description
        assert field.constraints == "minimum: 1"
    assert (
        "A gapmer design requires left_wing_length, gap_length, and "
        "right_wing_length."
    ) in rules
    assert (
        "An unmodified design must not define gapmer segment lengths."
    ) in rules


def test_json_file_contract_maps_to_its_serializable_class() -> None:
    target_step = get_built_in_step("create-target-gene")
    candidate_step = get_built_in_step("generate-antisense-candidates")

    assert json_contract_types(target_step.target_gene_output.file_type) == (
        TargetGene,
    )
    assert json_contract_types(candidate_step.therapeutics_output.file_type) == (
        ASO,
        Gapmer,
        siRNA,
    )
    assert candidate_step.therapeutics_output.file_type.value_type == list[
        AntisenseTherapeutic
    ]


def test_class_json_contract_owns_only_its_direct_fields() -> None:
    contract = serializable_contract_nodes(
        TargetGene,
        refdoc="api/modules/Targets",
    )
    reference = "\n".join(node.astext() for node in contract)
    links = [link for node in contract for link in node.findall(addnodes.pending_xref)]

    contract_section = contract[0]
    assert isinstance(contract_section, nodes.section)
    contract_title = contract_section.next_node(nodes.title)
    assert contract_title is not None
    assert contract_title.astext() == "File contract"
    assert "Example object" in reference
    assert "__class__" in reference
    assert "ASOkai.Targets._target_gene" in reference
    assert "sites" in reference
    assert "transcript_id" not in reference
    assert {link["reftarget"] for link in links} == {
        "ASOkai.Sites.GenomicSite",
        "ASOkai.Sites.TranscriptSite",
    }


def test_nested_classes_own_their_json_details() -> None:
    aso_contract = serializable_contract_nodes(
        ASO,
        refdoc="api/modules/Antisense",
    )
    gapmer_contract = serializable_contract_nodes(
        Gapmer,
        refdoc="api/modules/Antisense",
    )
    aso_fields = next(
        table.astext()
        for node in aso_contract
        for table in node.findall(nodes.table)
    )
    gapmer_fields = next(
        table.astext()
        for node in gapmer_contract
        for table in node.findall(nodes.table)
    )

    assert "chemistry" not in aso_fields
    assert "left_wing_length" not in aso_fields
    assert "gap_length" not in aso_fields
    assert "right_wing_length" not in aso_fields
    assert "chemistry" not in gapmer_fields
    assert "left_wing_length" in gapmer_fields
    assert "gap_length" in gapmer_fields
    assert "right_wing_length" in gapmer_fields


@pytest.mark.parametrize("serializable_type", [Oligonucleotide, siRNA])
def test_serializable_contract_describes_every_field(serializable_type: type) -> None:
    reference = "\n".join(
        node.astext()
        for node in serializable_contract_nodes(
            serializable_type,
            refdoc="api/modules/Antisense",
        )
    )

    assert "Meaning: —" not in reference


@pytest.mark.parametrize("serializable_type", [Chemistry, Site])
def test_abstract_serializable_class_has_no_json_contract(
    serializable_type: type,
) -> None:
    assert not serializable_contract_nodes(
        serializable_type,
        refdoc=f"api/modules/{serializable_type.__module__.split('.')[1]}",
    )


def test_serializable_contract_is_the_final_class_section() -> None:
    document = new_document("api/modules/Targets")
    module_section = nodes.section(ids=["targets"])
    module_section += nodes.title(text="Targets")
    description = addnodes.desc(objtype="class")
    description += addnodes.desc_signature(
        module="ASOkai.Targets",
        fullname="TargetGene",
    )
    description += addnodes.desc_content()
    module_section += description
    document += module_section

    append_serializable_contracts(
        SimpleNamespace(env=SimpleNamespace(docname="api/modules/Targets")),
        document,
    )

    content = description.next_node(addnodes.desc_content)
    assert isinstance(content, addnodes.desc_content)
    contract_section = content.children[-1]
    assert isinstance(contract_section, nodes.section)
    contract_title = contract_section.next_node(nodes.title)
    assert contract_title is not None
    assert contract_title.astext() == "File contract"
    assert list(contract_section.findall(nodes.table))


def test_json_contract_generates_valid_examples() -> None:
    for step in get_built_in_steps():
        for output in step.spec.outputs:
            if not isinstance(output.file_type, JsonFile):
                continue
            content = json_example(output.file_type)
            assert content
            output.file_type.loads(content, source="documentation test")


def test_class_contract_omits_an_invalid_schema_derived_example() -> None:
    contract = serializable_contract_nodes(
        TranscriptSite,
        refdoc="api/modules/Sites",
    )
    reference = "\n".join(node.astext() for node in contract)

    assert "File contract" in reference
    assert "Fields" in reference
    assert "Example object" not in reference


def test_local_contents_uses_internal_page_links() -> None:
    contents = local_contents([section("Example", [])])
    link = next(contents.findall(nodes.reference))

    assert link["refid"] == "example"
    assert "refuri" not in link


def test_opaque_outputs_use_human_readable_format_names() -> None:
    step = get_built_in_step("download-genome")
    reference = "\n".join(
        node.astext() for node in build_step_reference(step, _config_schema())
    )

    assert "gzip-compressed DNA FASTA" in reference
    assert "SQLite gffutils database" in reference
    assert "application/gzip" not in reference


def test_analysis_output_preserves_index_and_column_order() -> None:
    step = get_built_in_step("intrinsic-features")
    csv_file = step.spec.outputs[0].file_type
    assert isinstance(csv_file, CsvFile)
    generated_nodes = build_step_reference(step, _config_schema())
    reference = "\n".join(node.astext() for node in generated_nodes)
    ordered_columns = (
        "site_id",
        "GC_content",
        "AT_content",
        "T_count",
        "CpG_count",
        "T_content",
        "CpG_content",
    )

    positions = [reference.index(f"\n{column}\n") for column in ordered_columns]
    assert positions == sorted(positions)
    assert "proportion of Guanine" in reference
    assert "Accepted value: string" in reference
    assert "\nstr\n" not in reference
