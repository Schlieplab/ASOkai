#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool

baseCommand: intrinsic-features

doc: |
  Computes intrinsic features (GC content, T-runs, AT-runs) for each ASO
  target site. Output: analysis/intrinsic/{target_id}/{assembly}_{target_id}_intrinsic.json

requirements:
  WorkReuse:
    enableReuse: true

arguments:
  - prefix: --outdir
    valueFrom: "."

inputs:

  target_gene:
    type: File
    doc: Serialized target gene object from create-target-gene.
    inputBinding:
      prefix: --target-gene

  assembly:
    type: string
    doc: Assembly ID (e.g. GRCh38). Used in output filename.
    inputBinding:
      prefix: --assembly

  target_id:
    type: string?
    doc: Ensembl gene ID. Takes priority over target_name.
    inputBinding:
      prefix: --target-id

  target_name:
    type: string?
    doc: Gene name. Used if target_id is not provided.
    inputBinding:
      prefix: --target-name

outputs:

  intrinsic_features:
    type: File
    doc: Intrinsic features per site ({assembly}_{target_id}_intrinsic.json).
    outputBinding:
      glob: "*_intrinsic.json"
