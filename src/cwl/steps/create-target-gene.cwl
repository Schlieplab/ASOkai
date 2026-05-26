#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool

baseCommand: [ASOkai, step, create-target-gene]

doc: |
  Creates a target gene object from genome data and extracts ASO target sites.

requirements:
  WorkReuse:
    enableReuse: true

inputs:

  target_id:
    type: string?
    doc: Ensembl gene ID (e.g. ENSG00000133703). Takes priority over target_name.
    inputBinding:
      prefix: --target-id

  target_name:
    type: string?
    doc: Gene name (e.g. KRAS). Used if target_id is not provided.
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

  dna:
    type: File
    doc: Primary assembly FASTA from download-genome.
    inputBinding:
      prefix: --dna

  cdna:
    type: File
    doc: cDNA FASTA from download-genome.
    inputBinding:
      prefix: --cdna

  annotation:
    type: File
    doc: GTF annotation file from download-genome.
    inputBinding:
      prefix: --annotation

  assembly:
    type: string
    doc: Assembly ID (e.g. GRCh38).
    inputBinding:
      prefix: --assembly

  release:
    type: int
    doc: Ensembl release number (e.g. 114).
    inputBinding:
      prefix: --release

  species:
    type: string
    doc: Species name (e.g. Homo_sapiens).
    inputBinding:
      prefix: --species

  target_gene_output:
    type: string
    doc: Filename for the output JSON.
    inputBinding:
      prefix: --output

outputs:

  target_gene:
    type: File
    doc: Serialized target gene object.
    outputBinding:
      glob: $(inputs.target_gene_output)
