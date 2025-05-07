# ASO Design Pipeline

A comprehensive software package for designing Antisense Oligonucleotides (ASOs), specifically tailored for Gapmer ASOs targeting RNase-H1 mediated cleavage. The pipeline identifies optimal target sites based on sequence properties, thermodynamic parameters, and kinetic considerations.

## Features

- **Comprehensive ASO Design**: Identifies and evaluates potential ASO target sites based on multiple criteria
- **Thermodynamic Analysis**: Calculates binding energies and predicts RNA-RNA/DNA-RNA interactions
- **Off-target Analysis**: Identifies potential off-target binding sites across the transcriptome
- **Transcript-specific Analysis**: Considers transcript support levels (TSL) for more accurate targeting
- **Multi-species Support**: Currently supports human (Homo sapiens) and mouse (Mus musculus) genomes

## Dependencies

### Core Dependencies
- **Python 3.8+** ?????
- **Bowtie2**: For read alignment against genome and transcriptome
- **ViennaRNA**: For RNA secondary structure prediction and thermodynamic calculations (Currently using the python wrapper)

### Python Packages
```
biopython==1.85
gget==0.29.0
polars==1.29.0
setuptools==65.5.0
ViennaRNA==2.7.0
```

## Installation

1. **Install System Dependencies**

    A working installation of Bowtie2 is required. [[1]](#1)
   ```bash
   # For Ubuntu/Debian:
   sudo apt-get install bowtie2
   ```
   ```bash
   # For macOS:
   brew install bowtie2
   ```

2. **Install Python Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the Pipeline**
   - Copy `config.ini.example` to `config.ini`
   - Update the configuration parameters as needed

## Usage

### Basic Usage
```bash
python main.py --args DEFAULT --job <job_name>
```

### Command Line Arguments
- `--args` or `-as`: Configuration set to use from config.ini (default: "DEFAULT")
- `--job` or `-j`: Job name for organizing output files (optional)

### Configuration
The pipeline is configured through `config.ini`. Key parameters include:
- Genome assembly version
- Ensembl release version
- Target gene
- ASO length
- GC content bounds
- Transcript support levels
- Bowtie2 parameters
- Data directories

## Output Features

### Intrinsic Features
- **GC Content**: Both count and percentage of G/C bases ????
- **AT/T Runs**: Maximum length of continuous A/T or T sequences

### Extrinsic Features
- **dG-binding (Delta_G OT)**: The calculated Gibbs free energy change (ΔG) in kcal/mol, representing the predicted binding affinity between the candidate ASO and its primary target RNA sequence. Calculated using RNAcofold.

- **repeated-sites-count (OT binding multiplicity in mature mRNA)**: The count of locations *within the target gene's mature mRNA* (excluding the primary target site itself) where the candidate ASO potentially binds. This is determined by a calculated binding energy (ddG) below a specific threshold and the presence of a complementary "gap" region, indicating sites prone to RNase-H1 cleavage.

- **Specific-off-target-count**: The approximated (lower bound) count of locations *outside the intended target gene* (across the transcriptome/genome) where the candidate ASO potentially binds. This is also determined by a ddG below a specific threshold and a complementary "gap" region, highlighting potential off-targets prone to RNase-H1 cleavage.

- **Transcript-Prevalence-Ratio**: The fraction of the target gene's relevant transcripts (filtered by TSL - Transcript Support Level) that contain the specific binding site for the candidate ASO.

- **Ordered-Transcripts**: A comma-separated list of Ensembl transcript IDs for the target gene (filtered by TSL) that contain the primary binding site for the candidate ASO. ????

- **Ordered-exons**: A comma-separated list of Ensembl exon IDs corresponding to the exons within the `Ordered-Transcripts` that contain the primary binding site for the candidate ASO. ????

- **Ensembl-link**: A URL pointing to the Ensembl genome browser, displaying the specific genomic location of the candidate ASO's primary target site.

### Advanced Features

- **Multiplicities of inexactly matching sites prone for RNase H1 activity**:
  - Characterized by a large enough complementary substring in the middle of the ASO-RNA duplex (RNase H1 activity typically requires 5-10 consecutive matches, as per Crooke 2021).
  - Mismatches are tolerated primarily in the flanks (wings) of the Gapmer ASO.

- **Multiplicities of inexactly matching sites unlikely for RNase H1 activity**:
  - Characterized by mismatches within the central "gap" region of the ASO-RNA duplex.

- **Secondary target sites of oligo candidate**:
  - An ASO candidate has a reasonable binding affinity (e.g., ΔΔG within 5 kcal/mol of the primary target) to another location on the target gene, with a sufficiently complementary "gap" region.

- **Multiple Binding sites within one mRNA**: (Pedersen 2020) - Further details on how this is specifically calculated can be added.

- **Histogram of binned delta_delta_G**: For inexactly matching binding sites in the target pre-mRNA/mature mRNA. ????

## Directory Structure
```
ASODesignPipeline/
├── config.ini                    # Configuration file
├── main.py                      # Main pipeline script
├── requirements.txt             # Python dependencies
└── src/                        # Source code
    ├── oligo_extractor.py     # ASO candidate extraction logic
    └── utils/                 # Utility modules
        ├── file_operations.py # File handling utilities
        ├── genome.py         # Genome data handling
        ├── sequence_analysis.py # Sequence analysis functions
        └── time_utils.py     # Timing utilities
```

1.  Ensure all pre-requisites are met and configured.
2.  Prepare your `config.ini` file.
3.  Run `main.py` with appropriate command-line arguments:

    ```bash
    python main.py
    ```
    Refer to `python main.py --help` for all available options.


## References
<a id="1">[1]</a> 
Langmead, Ben, and Steven L. Salzberg. "Fast Gapped-Read Alignment with Bowtie 2." Nature Methods 9, no. 4 (April 2012): 357–59. https://doi.org/10.1038/nmeth.1923.

<a id="2">[2]</a>
Lorenz, Ronny, Stephan H. Bernhart, Christian Höner zu Siederdissen, Hakim Tafer, Christoph Flamm, Peter F. Stadler, and Ivo L. Hofacker. "ViennaRNA Package 2.0." Algorithms for Molecular Biology 6, no. 1 (November 24, 2011): 26. https://doi.org/10.1186/1748-7188-6-26.

<a id="3">[3]</a>
Cock, P. J. A., Antao, T., Chang, J. T., Chapman, B. A., Cox, C. J., Dalke, A., Friedberg, I., Hamelryck, T., de Hoon, M. J. L., Kurowski, K., Li, H., May, P., Nelson, D. R., Parry, M. A. L., Pachter, L., Penchovsky, R., Prlić, A., Talevich, E., Wilczyński, B., & Yoon, B. J. (2009). Biopython: freely available Python tools for computational molecular biology and bioinformatics. Bioinformatics, 25(11), 1422–1423. https://doi.org/10.1093/bioinformatics/btp163

<a id="4">[4]</a>
Luebbert, L., & Pachter, L. (2023). Efficient querying of genomic reference databases with gget. Bioinformatics. https://doi.org/10.1093/bioinformatics/btac836

<a id="5">[5]</a>
Polars contributors. Polars: Blazingly Fast DataFrames in Rust and Python. Available at: https://pypi.org/project/polars/ (Accessed: 6 May 2025).

## License
[Add your license information here]

## Contributing
[Add contribution guidelines here]