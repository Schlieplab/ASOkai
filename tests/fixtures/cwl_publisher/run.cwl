#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: Workflow
requirements:
  MultipleInputFeatureRequirement: {}
inputs: {}
steps:
  produce_dna:
    run: producer-a.cwl
    in: []
    out:
      - dna
  produce_target:
    run: producer-b.cwl
    in: []
    out:
      - target
  publish:
    run: publish.cwl
    in:
      files:
        source:
          - produce_dna/dna
          - produce_target/target
        linkMerge: merge_flattened
    out:
      - data
outputs:
  data:
    type: Directory
    outputSource: publish/data
