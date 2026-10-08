Build Bowtie 2 index
====================

.. asokai-step-reference:: build-bowtie2-index

.. note::

   This step invokes the third-party ``bowtie2-build`` executable. Bowtie 2 is
   GPLv3 software; ASOkai does not distribute or link against it. Install the
   executable through the supplied Conda environment.

Supply any plain FASTA reference. The index destination includes the Bowtie 2
build options. In the default signature validation mode, its receipt records
the selected FASTA input, so changing the reference causes a rebuild at the
same destination.

To index a target gene, name an ``instantiate-target-gene`` task run
``target_gene`` and link ``reference`` to its ``fasta`` output::

   runs:
     - task: instantiate-target-gene
       id: target_gene
     - step: build-bowtie2-index
       inputs:
         reference:
           from: run.target_gene.fasta

On the CLI, select an existing FASTA with::

   ASOkai run --no-config \
     --step build-bowtie2-index --input reference=path:/path/to/reference.fa

To link a named producer in the same CLI selection, use
``--input reference=from:run.target_gene.fasta`` after the index step.
