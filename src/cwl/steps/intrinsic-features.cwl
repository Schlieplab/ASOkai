#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool

baseCommand: [ASOkai, step, intrinsic-features]

doc: |
  Computes intrinsic features (GC content, T-runs, AT-runs) for each ASO target site.

requirements:
  WorkReuse:
    enableReuse: true

inputs:

  target_gene:
    type: File
    doc: Serialized target gene object from create-target-gene.
    inputBinding:
      prefix: --target-gene

  assembly:
    type: string
    doc: Assembly ID (e.g. GRCh38).
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

  k:
    type: int
    doc: ASO length.
    inputBinding:
      prefix: --k

  region:
    type:
      type: enum
      symbols: [exonic_only, pre-mrna, transcriptomic]
    doc: Target region type.
    inputBinding:
      prefix: --region

  intrinsic_features_output:
    type: string
    doc: Filename for the output JSON.
    inputBinding:
      prefix: --output

outputs:

  intrinsic_features:
    type: File
    doc: Intrinsic features per ASO target site.
    outputBinding:
      glob: $(inputs.intrinsic_features_output)
