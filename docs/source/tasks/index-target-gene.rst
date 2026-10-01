Index target gene
=================

.. asokai-runnable-reference:: task index-target-gene

This task accepts a target-gene JSON file, writes its sequence as FASTA, and
builds a six-file Bowtie 2 index. Supply the ``fasta`` child's ``target_gene``
input from an existing path or a named run. The task exposes the FASTA and
index directory as outputs.

For example, connect it to ``instantiate-target-gene`` in a ``runs`` selection::

   runs:
     - task: instantiate-target-gene
       id: gene
     - task: index-target-gene
       runs:
         - id: fasta
           inputs:
             target_gene:
               from: run.gene.target_gene
