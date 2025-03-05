import os
import gzip
import shlex
import subprocess
import configparser
import logging
from ftplib import FTP
from typing import Optional, List, Tuple, Dict, Any
from Bio import SeqIO
from pyensembl import Genome
from Bio.Seq import Seq
from gget import ref
import time
import re



# Create a configparser object and read the configuration file.
config = configparser.ConfigParser()
config.read('config.ini')

ALLOWED_SPECIES = {"human", "mouse"}


def extract_gene(fasta_gz_in: str, fasta_gz_out: str, gene_to_extract: str) -> None:
    """
    Extract a specific gene from a .fa.gz file and save the filtered sequences.
    """
    try:
        with gzip.open(fasta_gz_in, "rt") as infile, gzip.open(fasta_gz_out, "wt") as outfile:
            sequences = SeqIO.parse(infile, "fasta")
            filtered_sequences = (seq for seq in sequences if gene_to_extract in seq.description)
            SeqIO.write(filtered_sequences, outfile, "fasta")
    except OSError as e:
        logging.error("Error processing gene extraction files: %s", e)
        raise


def collect_scaffold(genome_assembly: int, ensembl_release: int) -> Optional[str]:
    """
    Download the specified human scaffold file from Ensembl if it is not already present.
    
    Parameters:
        genome_assembly (int): The genome assembly version (e.g., 38).
        ensembl_release (int): The Ensembl release version (e.g., 101).
    
    Returns:
        Optional[str]: File path to the scaffold file or None on download failure.
    """
    base_path: str = config['DEFAULT']['PyEnsemblDataDir']
    dir_path: str = os.path.join(base_path, f"pyensembl/GRCh{genome_assembly}/ensembl{ensembl_release}")
    filename: str = f"Homo_sapiens.GRCh{genome_assembly}.{ensembl_release}.chr_patch_hapl_scaff.gtf.gz"
    full_path: str = os.path.join(dir_path, filename)

    if not os.path.exists(full_path):  # Don't re-download.
        try:
            ftp = FTP('ftp.ensembl.org')
            ftp.login()
            ftp.cwd(f'pub/release-{ensembl_release}/gtf/homo_sapiens')
            os.makedirs(dir_path, exist_ok=True)
            with open(full_path, 'wb') as fp:
                ftp.retrbinary("RETR " + filename, fp.write)
            logging.info(f"Downloaded {filename} Scaffold")
        except Exception as e:
            logging.error(f"Could not collect Scaffold: {e}")
            return None
    else:
        logging.info(f"Using existing {filename} Scaffold")
    return full_path



def filter_transcripts_by_tsl(
    genome: Genome, 
    tsl_list: List[Optional[int]], 
    output_fasta: str
) -> None:
    """
    Filter transcripts from a genome object based on transcript support levels (TSL).
    
    This function uses PyEnsembl to extract transcripts and their metadata (including TSL)
    from the genome object. Only transcripts with a TSL value in `tsl_list` are written
    to the output FASTA file.
    
    Args:
        genome (Genome): PyEnsembl genome object with transcript data loaded.
        tsl_list (List[Optional[int]]): List of allowed TSL values (e.g., [1, 2, 3, None]).
        output_fasta (str): Path to the output FASTA file.
    """
    # Open the output FASTA file for writing
    with open(output_fasta, "w") as fout:
        for transcript in genome.transcripts():
            # Extract TSL from transcript metadata
            tsl = transcript.support_level
            if tsl in tsl_list:
                # Write transcript to output FASTA
                fout.write(f">{transcript.id} {transcript.gene_name}\n")
                fout.write(f"{transcript.sequence}\n")



def build_bowtie_index(e_release: int, g_assembly: int, species: str, bowtie_index: str, gene_id: str,
                         tsl: bool = False, tsl_list: Optional[list] = None, genome: Optional[Genome] = None, gene_only: bool = False) -> int:
    """
    Builds a Bowtie2 index for the specified species if not already present.
    
    Parameters:
        e_release (int): The Ensembl release version.
        g_assembly (int): The genome assembly version.
        species (str): The species ('human' or 'mouse').
        bowtie_index (str): Base name for the Bowtie2 index.
        gene_id (str): Gene identifier to extract if gene_only is True.
        tsl (bool, optional): Whether to filter transcripts by transcript support level.
        tsl_list (list, optional): transcript support levels. i.e. [1,2,4,None]. Required if tsl is True.
        genome (Genome, optional): PyEnsembl genome object. Required if tsl is True.
        gene_only (bool, optional): Whether to index only one gene.
    
    Returns:
        int: Return code from the Bowtie2 build command (0 indicates success).
    """
    if species not in ALLOWED_SPECIES:
        msg = "Invalid species provided. Only human and mouse are supported."
        logging.error(msg)
        raise ValueError(msg)

    logging.info("Running Bowtie2 index build")
    
    base_pyensembl = config["DEFAULT"]["PyEnsemblDataDir"]
    if species == 'human':
        input_file = os.path.join(base_pyensembl,
                                 f"pyensembl/GRCh{g_assembly}/ensembl{e_release}",
                                 f"Homo_sapiens.GRCh{g_assembly}.cdna.all.fa.gz")
    else:  # species == 'mouse'
        input_file = os.path.join(base_pyensembl,
                                 f"pyensembl/GRCm{g_assembly}/ensembl{e_release}",
                                 f"Mus_musculus.GRCm{g_assembly}.cdna.all.fa.gz")

    if gene_only:
        input_file = f"{os.path.splitext(input_file)[0]}_{gene_id}_only.cdna.all.fa.gz"
        bowtie_index_base = f"{bowtie_index}_{gene_id}_only"
        extract_gene(input_file, input_file, gene_id)
    elif tsl:
        # Create a new filename for the filtered FASTA
        bowtie_index_base = bowtie_index
        filtered_file = f"{os.path.splitext(input_file)[0]}_filtered.cdna.all.fa.gz"
        logging.info("Filtering %s for transcript support levels: %s", input_file, tsl_list)
        try:
            filter_transcripts_by_tsl(genome, tsl_list, filtered_file)
            input_file = filtered_file  # Update input_file to use the filtered version
        except Exception as e:
            logging.error("Transcript filtering failed: %s", e)
            return 1
    else:
        bowtie_index_base = bowtie_index
        
        
    bowtie_dir = os.path.join(config['DEFAULT']['Bowtie2Dir'], "bowtie2Home", bowtie_index)

    try:
        files_in_dir = os.listdir(bowtie_dir)
    except OSError as e:
        logging.error("Error reading directory %s: %s", bowtie_dir, e)
        return 1

    file_exists = any(file.startswith(bowtie_index_base + ".") for file in files_in_dir)
    if not file_exists:
        index_prefix = os.path.join(bowtie_dir, bowtie_index_base)
        command = f"bowtie2-build {input_file} {index_prefix} {config['DEFAULT']['BowtieBuildIndexArg']}"
        logging.info("Executing command: %s", command)
        try:
            result = subprocess.run(shlex.split(command), check=True, capture_output=True, text=True)
            return result.returncode
        except subprocess.CalledProcessError as e:
            logging.error("bowtie2-build failed: %s", e.stderr)
            raise RuntimeError("Bowtie2 index build failed.") from e
    else:
        logging.info("Using existing index: %s", bowtie_index_base)
        return 0


def run_bowtie(in_file: str,
               bowtie_index: str,
               bowtie_args: str,
               gene_only: bool = False,
               gene_id: Optional[str] = None,
               trim: bool = False,
               multiplicity_layout: Optional[List[int]] = None) -> str:
    """
    Execute Bowtie2 alignment for the k-mers.

    Parameters:
        in_file (str): Path to the input file.
        bowtie_index (str): Path to the Bowtie2 index.
        bowtie_args (str): Additional command-line arguments for Bowtie2.
        gene_only (bool): If True, aligns only to the target gene region.
        gene_id (Optional[str]): The gene identifier to use for gene_only alignment. Required if gene_only is True.
        trim (bool): If True, apply trimming options.
        multiplicity_layout (Optional[List[int]]): A sequence containing at least three integers.
            When trim is True, the first and third elements are used for '--trim5' and '--trim3', respectively.

    Returns:
        str: The path to the output SAM file.
    """
    if gene_only:
        logging.info("Running Bowtie2 alignment for target gene")
        if not gene_id:
            msg = "gene_id must be provided when gene_only is True."
            logging.error(msg)
            raise ValueError(msg)
        # Build updated bowtie_index path for gene-only case.
        bowtie_index = os.path.join(os.path.dirname(bowtie_index),
                                    os.path.basename(bowtie_index),
                                    os.path.basename(bowtie_index) + f"_{gene_id}_only")
        out_file = f"{os.path.splitext(in_file)[0]}_{gene_id}_only.sam"
    else:
        logging.info("Running Bowtie2 alignment")
        bowtie_index = os.path.join(os.path.dirname(bowtie_index),
                                    os.path.basename(bowtie_index),
                                    os.path.basename(bowtie_index))
        out_file = f"{os.path.splitext(in_file)[0]}.sam"



    if trim:
        if not multiplicity_layout or len(multiplicity_layout) < 3:
            msg = "When trim is True, multiplicity_layout must contain at least three integers."
            logging.error(msg)
            raise ValueError(msg)
        trim5_val = str(multiplicity_layout[0])
        trim3_val = str(multiplicity_layout[2])
        out_file = f"{os.path.splitext(out_file)[0]}_trimmed.sam"


    # Build the initial command as a list to avoid shell injection issues.
    command = ["bowtie2", "-x", bowtie_index, "-U", in_file, "-S", out_file]
    if bowtie_args:
        command.extend(shlex.split(bowtie_args))
    if trim:
        command.extend(["--trim5", trim5_val, "--trim3", trim3_val])
        
    logging.info("Executing Bowtie2 command: %s", " ".join(command))
    start_time = time.time()
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        logging.error("Bowtie2 execution failed: %s", e.stderr.strip())
        raise RuntimeError("Bowtie2 execution failed.") from e

    elapsed = time.time() - start_time
    logging.info("Bowtie2 processing time: %.2f seconds", elapsed)
    return out_file

    
def build_RNAcofold_in(cofold_in: str, kmers: List[Tuple[str, str]], 
                    targets: Optional[Dict[str, List[Tuple[Any, str]]]] = None) -> None:
    """
    Builds an input file for RNAcofold analysis from filtered k-mers.
    
    Parameters:
        cofold_in (str): Path to the output file for RNAcofold input.
        kmers (List[Tuple[str, str]]): List of tuples containing k-mer identifier and sequence.
        targets (Optional[Dict[str, List[Tuple[Any, str]]]]): Optional mapping of k-mer identifiers to target sequences.
            If provided, the reverse complement of these target sequences will be used.
    
    Returns:
        None

    Example:
    >>> kmers = [('S000001', 'ATCG'), ('S000002', 'GCTA')]
    >>> targets = {'S000001': [(_, 'GGTT'), (_, 'AACC')], 'S000002': [(_, 'TTAA')]}
    >>> build_RNAcofold_in('/path/to/cofold_input.txt', kmers, targets)
    """
    directory: str = os.path.dirname(cofold_in)
    os.makedirs(directory, exist_ok=True)

    with open(cofold_in, "w") as filtered_kmer_file:
        if targets:
            for kmer_id, seq in kmers:
                if kmer_id in targets:
                    for i, target in enumerate(targets[kmer_id]):
                        # Write header and sequence lines.
                        filtered_kmer_file.write(f">{kmer_id}_{i}\n")
                        filtered_kmer_file.write(f"{seq}&{str(Seq(target[1]).reverse_complement())}\n")
                else:
                    logging.warning(f"No target found for k-mer {kmer_id}, skipping targets.")
        else:
            for kmer_id, seq in kmers:
                filtered_kmer_file.write(f">{kmer_id}\n")
                filtered_kmer_file.write(f"{seq}&{str(Seq(seq).reverse_complement())}\n")
                
                
def build_RNAduplex_in(duplex_in: str, kmers: List[Tuple[str, str]], 
                       targets: List[Tuple[str, str]]) -> None:
    """
    Builds an input file for RNAduplex analysis from filtered k-mers.
    
    Parameters:
        duplex_in (str): Path to the output file for RNAduplex input.
        kmers (List[Tuple[str, str]]): List of tuples containing k-mer identifier and sequence.
        targets (List[Tuple[str, str]]): target sequences that will be prepended to the reverse complement
                      of each k-mer sequence.
    
    Returns:
        None
    """
    directory: str = os.path.dirname(duplex_in)
    os.makedirs(directory, exist_ok=True)

    with open(duplex_in, "w") as filtered_kmer_file:
        for kmer_id, seq in kmers:
            seq = str(Seq(seq).reverse_complement())
            for target_id, target_seq in targets:
                # Write header and sequence lines.
                filtered_kmer_file.write(f">{kmer_id}_{target_id}\n")
                filtered_kmer_file.write(f"{target_seq}&{seq}\n")
                
def run_RNAcofold(rnaCofoldInFile: str, paramFile: str) -> str:
    """
    Run RNAcofold to calculate RNA secondary structure energies and save the results to a CSV file.

    Parameters:
        rnaCofoldInFile (str): Path to the RNA sequences input file for RNAcofold.
        paramFile (str): Parameter file for RNAcofold.

    Returns:
        str: The path to the output CSV file containing RNAcofold results.
    """
    outFile = os.path.splitext(rnaCofoldInFile)[0] + "_cofold_out.csv"
    logging.info("Running RNAcofold")
    command = f'RNAcofold -p0 --output-format=D --jobs=0 --noPS --noconv {rnaCofoldInFile} {paramFile}'
    logging.info(f"Command: {command}")

    with open(outFile, 'w') as rcfOutFile:
        process = subprocess.Popen(
            shlex.split(command), stdout=rcfOutFile, stderr=subprocess.PIPE, text=True
        )
        while True:
            output = process.stderr.readline()
            if output:
                logging.info(output.strip())
        process.wait()
    return outFile
