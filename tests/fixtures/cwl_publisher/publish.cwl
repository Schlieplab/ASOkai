#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool
baseCommand:
  - ASOkai
  - publish-outputs
inputs:
  manifest:
    type: File
    default:
      class: File
      location: output-layout.yml
    inputBinding:
      position: 0
  files:
    type:
      type: array
      items: File
    inputBinding:
      position: 1
outputs:
  data:
    type: Directory
    outputBinding:
      glob: published/GRCh38
