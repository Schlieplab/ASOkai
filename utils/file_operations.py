import os
import gzip
import shlex
import subprocess
import configparser
import logging
from typing import Optional, List, Tuple, Dict, Any
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from pyensembl import Genome
import time
import gget
import urllib.request, urllib.parse



# Create a configparser object and read the configuration file.
config = configparser.ConfigParser()
config.read('config.ini')

ALLOWED_SPECIES = {"human", "mouse"}

def download_genome(index_name: str) -> Tuple[str, str, str, Optional[str]]:
    # Retrieve the file URLs from gget.ref
    gtf_url, cdna_url, pep_url = tuple(
        gget.ref("homo_sapiens", which=["gtf", "cdna", "pep"], release=113, ftp=True)
    )

    gtf_name = os.path.basename(urllib.parse.urlparse(gtf_url).path)
    cdna_name = os.path.basename(urllib.parse.urlparse(cdna_url).path)
    pep_name = os.path.basename(urllib.parse.urlparse(pep_url).path)

    genome_data_dir = os.path.join(config.get('GenomeDir', '.'), 'genome', index_name)
    os.makedirs(genome_data_dir, exist_ok=True)
    
    scaffold_gtf_path = None
    if config.get('Species', 'human') == 'human':     
        scaffold_gtf_url = gtf_url.replace('.gtf.gz', '.chr_patch_hapl_scaff.gtf.gz')
        
        scaffold_gtf_name = os.path.basename(urllib.parse.urlparse(scaffold_gtf_url).path)
        scaffold_gtf_path = os.path.join(genome_data_dir, scaffold_gtf_name)
        if not os.path.exists(scaffold_gtf_path):
            urllib.request.urlretrieve(scaffold_gtf_url, scaffold_gtf_path)
        else:
            logging.info("Scaffold GTF file already exists at '%s'", scaffold_gtf_path)
            
            
    gtf_path = os.path.join(genome_data_dir, gtf_name)
    cdna_path = os.path.join(genome_data_dir, cdna_name)
    pep_path = os.path.join(genome_data_dir, pep_name)

    # Download each file (if not already present)
    if not os.path.exists(gtf_path):
        urllib.request.urlretrieve(gtf_url, gtf_path)
    else:
        logging.info("GTF file already exists at '%s'", gtf_path)
    if not os.path.exists(cdna_path):
        urllib.request.urlretrieve(cdna_url, cdna_path)
    else:
        logging.info("cDNA file already exists at '%s'", cdna_path)
    if not os.path.exists(pep_path):
        urllib.request.urlretrieve(pep_url, pep_path)
    else:
        logging.info("Pep file already exists at '%s'", pep_path)

    # Optionally return the file paths (including our scaffold_gtf_path)
    return gtf_path, cdna_path, pep_path, scaffold_gtf_path


def extract_gene(
    fasta_gz_in: str, 
    fasta_gz_out: str, 
    gene_id: str,
    ) -> None:
    """
    Extract a specific gene from a .fa.gz file and save the filtered sequences.
    
    """
    try:
        with gzip.open(fasta_gz_in, "rt") as infile, gzip.open(fasta_gz_out, "wt") as outfile:
            sequences = SeqIO.parse(infile, "fasta")
            filtered_sequences = (seq for seq in sequences if gene_id in seq.description)
            SeqIO.write(filtered_sequences, outfile, "fasta")
    except OSError as e:
        logging.error("Error processing gene extraction files: %s", e)
        raise


def filter_transcripts_by_tsl(
    fasta_gz_in: str,
    fasta_gz_out: str,
    genome: Genome,
    tsl_list: List[Optional[int]],
    ) -> None:
    """
    Filter transcripts from a gzipped FASTA file based on transcript support levels using the
    genome object for transcript details. The filtered sequences are written to a gzipped FASTA file.
    
    Args:
        fasta_gz_in (str): Path to the input gzipped FASTA file containing transcript records.
        fasta_gz_out (str): Path to the output gzipped FASTA file.
        genome (Genome): Genome object that provides transcript details via a transcripts() method.
        tsl_list (List[Optional[int]]): List of allowed transcript support level values (e.g., [1, 2, 3, None]).
    """
    logging.info("Filtering %s for transcript support levels: %s", genome.annotation_name, tsl_list)

    tsl_set = set(tsl_list)

    transcript_to_gene = {}
    for t in genome.transcripts():
        if t.support_level in tsl_set:
            transcript_to_gene[t.id] = t.gene_name
    
    # Process in batches to reduce the number of write operations
    batch_size = 1000
    
    with gzip.open(fasta_gz_in, "rt") as infile, gzip.open(fasta_gz_out, "wt") as outfile:
        batch = []
        for seq in SeqIO.parse(infile, "fasta"):
            transcript_id = seq.id.split('.')[0]
            if transcript_id in transcript_to_gene:
                # Create a new SeqRecord with just the gene name as the description
                # This will result in a FASTA header like ">seq.id gene_name"
                new_record = SeqRecord(
                    seq.seq,
                    id=seq.id,
                    description=transcript_to_gene[transcript_id]
                )
                batch.append(new_record)
                
                if len(batch) >= batch_size:
                    SeqIO.write(batch, outfile, "fasta")
                    batch = []
        
        # Write any remaining records
        if batch:
            SeqIO.write(batch, outfile, "fasta")
        
    logging.info("Transcript filtering completed.")


def build_bowtie_index(input_path: str, index_name: str, 
                       tsl: bool = False, tsl_list: Optional[list] = None, genome: Optional[Genome] = None, 
                       gene_only: Optional[bool] = False, gene_id: Optional[str] = None) -> None:
    """
    Builds a Bowtie2 index for the specified species if not already present.
    
    Parameters:
        input_path (str): Path to the input FASTA file.
        index_name (str): Base name for the Bowtie2 index.
        tsl (bool, optional): Whether to filter transcripts by transcript support level.
        tsl_list (list, optional): transcript support levels. i.e. [1,2,4,None]. Required if tsl is True.
        genome (Genome, optional): PyEnsembl genome object. Required if tsl is True.
        gene_only (bool, optional): Whether to index only one gene.
        gene_id (str): Gene identifier to extract if gene_only is True.

    
    Returns:
        None
    """

    # TODO: change tsl namings for index
    
    # Build dynamic log message based on parameters
    log_msg = f"building bowtie index for {index_name}"
    if tsl:
        log_msg += f" with tsl active, tsl_list={tsl_list}"
    if gene_only:
        log_msg += f" and gene_only active, gene_id={gene_id}"
    logging.info(log_msg)

    if tsl:
        # Create a new filename for the filtered FASTA
        tsl_input_path = input_path.replace('.all.fa.gz', f'.tsl{"_".join(map(str, tsl_list))}.fa.gz')
        filter_transcripts_by_tsl(input_path, tsl_input_path, genome, tsl_list)
        input_path = tsl_input_path
        
    bowtie_dir = os.path.join(config['DEFAULT']['Bowtie2Dir'], "bowtie2Home", index_name)
    os.makedirs(bowtie_dir, exist_ok=True)
    
    if gene_only:
        gene_input_path = input_path.replace('.all.fa.gz', f'.{gene_id}.fa.gz')
        extract_gene(input_path, gene_input_path, gene_id)
        input_path = gene_input_path
        index_name = f"{index_name}_{gene_id}_only"


    try:
        files_in_dir = os.listdir(bowtie_dir)
    except OSError as e:
        logging.error("Error reading directory %s: %s", bowtie_dir, e)
        return 1

    file_exists = any(file.startswith(index_name + ".") for file in files_in_dir)
    if not file_exists:
        index_prefix = os.path.join(bowtie_dir, index_name)
        command = f"bowtie2-build {input_path} {index_prefix} {config['DEFAULT']['BowtieBuildIndexArg']}"
        logging.info("Executing command: %s", command)
        
        result = subprocess.run(shlex.split(command), check=True, capture_output=True, text=True)
        logging.info("Bowtie2 index build completed.")
        return result.returncode

    else:
        logging.info("Using existing index: %s", index_name)
        return


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
                
                
def run_RNAcofold(cofold_in_file: str, param_file: str) -> str:
    """
    Run RNAcofold to calculate RNA secondary structure energies and save the results to a CSV file.

    Parameters:
        cofold_in_file (str): Path to the RNA sequences input file for RNAcofold.
        param_file (str): Parameter file for RNAcofold.

    Returns:
        str: The path to the output CSV file containing RNAcofold results.
    """
    outFile = os.path.splitext(cofold_in_file)[0] + "_cofold_out.csv"
    logging.info("Running RNAcofold")
    command = f'RNAcofold -p0 -d1 --output-format=D --jobs=0 --noPS --noconv {cofold_in_file} {param_file}'
    logging.info(f"Command: {command}")

    with open(outFile, 'w') as rcfOutFile:
        process = subprocess.Popen(
            shlex.split(command), stdout=rcfOutFile, stderr=subprocess.PIPE, text=True
        )
        # Read stderr in real time until the process ends
        while True:
            output = process.stderr.readline()
            if output == "" and process.poll() is not None:
                # No more output and process has finished, so exit loop
                break
            if output:
                logging.info(output.strip())
        process.wait()
    return outFile