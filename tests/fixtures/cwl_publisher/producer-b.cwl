#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool
baseCommand:
  - sh
  - -c
arguments:
  - printf target > target.json
inputs: {}
outputs:
  target:
    type: File
    outputBinding:
      glob: target.json
