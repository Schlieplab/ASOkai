#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool

baseCommand: download-genome

doc: |
  Download genome DNA (primary assembly FASTA), cDNA (FASTA), and annotation
  (GTF) from the Ensembl FTP server.
  Files are written to:
    ensembl/{assembly}/{release}/

requirements:
  NetworkAccess:
    networkAccess: true
  WorkReuse:
    enableReuse: true

arguments:
  - prefix: --outdir
    valueFrom: "."

inputs:

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

outputs:

  dna:
    type: File
    doc: Primary assembly DNA FASTA ({Species}.{Assembly}.dna.primary_assembly.fa.gz)
    outputBinding:
      glob: "ensembl/*/*/*.dna.primary_assembly.fa.gz"

  cdna:
    type: File
    doc: cDNA FASTA ({Species}.{Assembly}.cdna.all.fa.gz)
    outputBinding:
      glob: "ensembl/*/*/*.cdna.all.fa.gz"

  annotation:
    type: File
    doc: Gene annotation GTF ({Species}.{Assembly}.{release}.gtf.gz)
    outputBinding:
      glob: "ensembl/*/*/*.gtf.gz"
