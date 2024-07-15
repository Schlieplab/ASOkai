# ASO-design-pipeline

This will be a software package that helps the ASO design process to find optimal target sites based on a gene, it's sequence properties, thermodynamic and kinetic parameters.

## Packages & tools

* pyensembl: python library to connect to ENSEMBL (https://pyensembl.readthedocs.io/en/latest/pyensembl.html)
* Bowtie2: Used for read alignment against genome
* RNAcofold (ViennaRNA): Calculating dG (affinity)


## Status Quo

`main.py` takes a gene id from ENsembl and a k-mer length as input. Genome and annotation release are configurable. Paths to bowtie and pyensemble are hard coded as of right now. Output is a csv file containing a list of distinct oligo candidates (reverse complement of target sites) targeting the input gene.

e.g.: KRAS 16 mers should result in 7402 candidate oligos.


## Overview of ASO features

The aim of this software is to give an overview of thermodynamic and kinetic calculations and prediction on which ASO candidates can be evaluated. The user, possibly working on experiments in ASO drug design, can select and filter based on these parameters the ASO candidates.

### Intrinsic features:
* GC content (proportion 0.0-1.0)
* Longest AT-run: defined as the longest subsequence only consisting of As and Ts (#nts, or %, or proportion 0.0-1.0)
* Longest T-run: defined as the longest subsequence only consisting of Ts (#nts, or %, or proportion 0.0-1.0)


### Extrinsic features:
* Delta_G of oligo-target (OT) complex [kcal per mol]
* OT binding multiplicity: How often can the target site be found in pre-mRNA
    * What is the equivalent of the pre-mRNA in the pyensemble objects?
    * Does this feature sum up the binding sites over all available transcripts? Dow we only take the most prominent transcript per protein?
* Multiplicities of inexactly matching sites prone for RNase H1 activity:
    * a large enough substring in the middle in common (RNASE H1 activity starts at 5 consecutive matches, best activity 8-10, Review Crooke 2021)
    * mismatches only in the flanks
* Multiplicities of inexactly matching sites unlikely for RNase H1 activity:
    * mismatches in the center of oligos
* secondary target sites of oligo candidate:
    * an oligo candidate has a reasonable (e.g. ddG=5) binding affinity to some other location on the target gene plus a large enough substring in the middle in common (RNASE H1 activity starts at 5 consecutive matches, best activity 8-10, Review Crooke 2021)
* Multiple Binding sites within one mRNA: Pedersen 2020
* Histogram of binned delta_delta_G for inexactly matching binding sites in target pre-mRNA


## Pre-requisites

* Working installation of Bowtie2 (path for bowtie index needs to be stated in config
* pyensemble, biopython
* RNAcofold (command line tool from ViennaRNA)

