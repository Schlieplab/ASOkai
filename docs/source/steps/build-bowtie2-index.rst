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
