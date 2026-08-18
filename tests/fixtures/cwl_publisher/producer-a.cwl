#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool
baseCommand:
  - sh
  - -c
arguments:
  - printf dna > dna.fa.gz
inputs: {}
outputs:
  dna:
    type: File
    outputBinding:
      glob: dna.fa.gz
