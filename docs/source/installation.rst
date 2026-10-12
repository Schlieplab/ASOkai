Installation
============

ASOkai needs Python 3.10 to 3.12 and the external programs KMC and Bowtie 2.

With Conda
----------

Conda installs KMC and Bowtie 2 alongside the Python dependencies, on Linux
and macOS:

.. code-block:: bash

   conda env create -f environment.yaml
   conda activate ASOkai
   python -m pip install -e .

Replace the last line with ``python -m pip install -e ".[dev]"`` to add the
contributor tools: pytest, pyright, black, pre-commit, cwltool, and Sphinx.

Windows
-------

Bioconda publishes no Windows packages, so KMC and Bowtie 2 cannot come from
the Conda environment there. Instructions for installing them separately will
be added.

Verify
------

.. code-block:: bash

   asokai list steps

The command prints the installed steps. ``ASOkai`` is an equivalent command
name.

Analyses that run on worker processes require ``fork`` and so use it only on
Linux. Elsewhere they run on worker threads, which produces the same results
and takes longer.

Next, the :doc:`Getting Started <getting-started>` guide configures and runs
the pipeline.
