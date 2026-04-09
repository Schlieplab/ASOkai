#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: Workflow

doc: |
  Full ASOkai standard pipeline:
    1. download-genome (fetch genome sequences and annotation)
    2. create-target-gene (build target gene object with ASO sites)
    3. intrinsic-features (compute intrinsic features per site)

inputs:
  assembly:    {type: string,  doc: "Assembly ID (e.g. GRCh38)."}
  release:     {type: int,     doc: "Ensembl release number."}
  species:     {type: string,  doc: "Species name (e.g. Homo_sapiens)."}
  target_id:   {type: string?, doc: "Ensembl gene ID (e.g. ENSG00000133703). Takes priority over target_name."}
  target_name: {type: string?, doc: "Gene name (e.g. KRAS). Used if target_id is not provided."}
  k:           {type: int,     doc: "ASO length."}
  region:
    type:
      type: enum
      symbols: [exonic_only, pre-mrna, transcriptomic]
    doc: Target region type.

steps:

  download:
    run: ../steps/download-genome.cwl
    in:
      assembly: assembly
      release:  release
      species:  species
    out: [dna, cdna, annotation]

  create_target_gene:
    run: ../steps/create-target-gene.cwl
    in:
      target_id:   target_id
      target_name: target_name
      k:           k
      region:      region
      dna:         download/dna
      cdna:        download/cdna
      annotation:  download/annotation
      assembly:    assembly
      species:     species
    out: [target_gene]

  intrinsic:
    run: ../steps/intrinsic-features.cwl
    in:
      target_gene: create_target_gene/target_gene
      assembly:    assembly
      target_id:   target_id
      target_name: target_name
    out: [intrinsic_features]

outputs:

  target_gene:
    type: File
    outputSource: create_target_gene/target_gene

  intrinsic_features:
    type: File
    outputSource: intrinsic/intrinsic_features
