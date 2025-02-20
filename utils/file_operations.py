import os
import gzip
import shlex
import subprocess
import configparser
import logging
from ftplib import FTP
from typing import Optional, List, Tuple, Dict, Any
from Bio import SeqIO
from Bio.Seq import Seq
from gget import ref
import requests

# Create a configparser object and read the configuration file.
config = configparser.ConfigParser()
config.read('config.ini')


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


def build_bowtie_index(e_release: int, g_assembly: int, species: str, bowtie_index_name: str,
                        gene_id: str, gene_only: bool = False) -> int:
    """
    Builds a Bowtie2 index for the specified species if not already present.
    
    Parameters:
        e_release (int): The Ensembl release version.
        g_assembly (int): The genome assembly version.
        species (str): The species ('human' or 'mouse').
        bowtie_index_name (str): Base name for the Bowtie2 index.
        gene_id (str): Gene identifier to extract if gene_only is True.
        gene_only (bool, optional): Whether to index only one gene.
    
    Returns:
        int: Return code from the Bowtie2 build command (0 indicates success).
    """
    def extract_gene(fasta_gz_in: str, fasta_gz_out: str, gene_to_extract: str) -> None:
        """Extract a specific gene from a .fa.gz file and save the filtered sequences."""
        with gzip.open(fasta_gz_in, "rt") as infile, gzip.open(fasta_gz_out, "wt") as outfile:
            sequences = SeqIO.parse(infile, "fasta")
            filtered_sequences = (seq for seq in sequences if gene_to_extract in seq.description)
            SeqIO.write(filtered_sequences, outfile, "fasta")

    logging.info("Running Bowtie2 index build")
    if species == 'human':
        cdna_file: str = os.path.join(
            config["DEFAULT"]["PyEnsemblDataDir"],
            f"pyensembl/GRCh{g_assembly}/ensembl{e_release}",
            f"Homo_sapiens.GRCh{g_assembly}.cdna.all.fa.gz"
        )
        local_file: str = os.path.join(
            config["DEFAULT"]["PyEnsemblDataDir"],
            f"pyensembl/GRCh{g_assembly}/ensembl{e_release}",
            f"Homo_sapiens.GRCh{g_assembly}.cdna.{gene_id}_only.fa.gz"
        )
    elif species == 'mouse':
        cdna_file = os.path.join(
            config["DEFAULT"]["PyEnsemblDataDir"],
            f"pyensembl/GRCm{g_assembly}/ensembl{e_release}",
            f"Mus_musculus.GRCm{g_assembly}.cdna.all.fa.gz"
        )
        local_file = os.path.join(
            config["DEFAULT"]["PyEnsemblDataDir"],
            f"pyensembl/GRCm{g_assembly}/ensembl{e_release}",
            f"Mus_musculus.GRCm{g_assembly}.cdna.{gene_id}_only.fa.gz"
        )
    else:
        logging.error("Invalid species (Only mouse and human).")
        return 1

    if gene_only:
        bowtie_index_name = f"{bowtie_index_name}_{gene_id}_only"
        extract_gene(cdna_file, local_file, gene_id)

    # Check if index already exists.
    bowtie_dir: str = os.path.join(config['DEFAULT']['Bowtie2Dir'], "bowtie2Home")
    try:
        files_in_dir: List[str] = os.listdir(bowtie_dir)
    except Exception as e:
        logging.error(f"Error reading directory {bowtie_dir}: {e}")
        return 1

    file_exists: bool = any(file.startswith(bowtie_index_name + ".") for file in files_in_dir)
    
    if not file_exists:
        input_file: str = local_file if gene_only else cdna_file
        command: str = (
            f"bowtie2-build {input_file} "
            f"{os.path.join(bowtie_dir, bowtie_index_name)} "
            f"{config['DEFAULT']['BowtieBuildIndexArg']}"
        )
        logging.info(f"Command: {command}")
        try:
            result = subprocess.run(shlex.split(command), check=True, capture_output=True, text=True)
            logging.info(f"bowtie2-build output: {result.stdout}")
            return result.returncode
        except subprocess.CalledProcessError as e:
            logging.error(f"bowtie2-build failed: {e.stderr}")
            return e.returncode
    else:
        logging.info(f"Using existing index: {bowtie_index_name}")
        return 0


def build_cofold_in(cofold_in: str, kmers: List[Tuple[str, str]], 
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
    >>> build_cofold_in('/path/to/cofold_input.txt', kmers, targets)
    """
    directory: str = os.path.dirname(cofold_in)
    os.makedirs(directory, exist_ok=True)

    with open(cofold_in, "w") as filteredkmerfile:
        if targets:
            for kmer_id, seq in kmers:
                if kmer_id in targets:
                    for i, target in enumerate(targets[kmer_id]):
                        # Write header and sequence lines.
                        filteredkmerfile.write(f">{kmer_id}_{i}\n")
                        filteredkmerfile.write(f"{seq}&{str(Seq(target[1]).reverse_complement())}\n")
                else:
                    logging.warning(f"No target found for k-mer {kmer_id}, skipping targets.")
        else:
            for kmer_id, seq in kmers:
                filteredkmerfile.write(f">{kmer_id}\n")
                filteredkmerfile.write(f"{seq}&{str(Seq(seq).reverse_complement())}\n")