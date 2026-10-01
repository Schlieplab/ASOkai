Index target gene
=================

.. asokai-runnable-reference:: task index-target-gene

This task writes a target-gene sequence as FASTA and builds a six-file Bowtie 2
index. Its ``fasta`` child uses ``create-target-gene`` by default. Supply an
existing path or a named run for the child's ``target_gene`` input to use a
different target. The task exposes the FASTA and index directory as outputs.

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
