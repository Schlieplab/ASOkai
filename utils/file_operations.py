import os
import gzip
import shlex
import subprocess
import logging
from typing import Optional, List, Tuple, Dict, Any
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from src.oligo_extractor import TargetSite
from pyensembl import Genome
import time
import gget
import urllib.request, urllib.parse




def download_genome(
    species: str,
    e_release: int,
    genome_dir: str,
    ) -> Tuple[str, str, str, Optional[str]]:
    """
    Download the genome files for a specified species.
    
    Args:
        species (str): Species name. e.g., 'homo_sapiens'.
        e_release (int): The Ensembl release version.
        genome_dir (str): Path to the directory where the genome files will be saved.
        
    Returns:
        Tuple[str, str, str, Optional[str]]: Paths to the GTF, cDNA, and peptide files, and an optional scaffold GTF path.
    """
    # Retrieve the file URLs from gget.ref
    gtf_url, cdna_url, pep_url = tuple(
        gget.ref(species, which=["gtf", "cdna", "pep"], release=e_release, ftp=True)
    )

    gtf_name = os.path.basename(urllib.parse.urlparse(gtf_url).path)
    cdna_name = os.path.basename(urllib.parse.urlparse(cdna_url).path)
    pep_name = os.path.basename(urllib.parse.urlparse(pep_url).path)

    
    scaffold_gtf_path = None
    if species == 'homo_sapiens':     
        scaffold_gtf_url = gtf_url.replace('.gtf.gz', '.chr_patch_hapl_scaff.gtf.gz')
        
        scaffold_gtf_name = os.path.basename(urllib.parse.urlparse(scaffold_gtf_url).path)
        scaffold_gtf_path = os.path.join(genome_dir, scaffold_gtf_name)
        if not os.path.exists(scaffold_gtf_path):
            urllib.request.urlretrieve(scaffold_gtf_url, scaffold_gtf_path)
        else:
            logging.info("Scaffold GTF file already exists at '%s'", scaffold_gtf_path)
            
            
    gtf_path = os.path.join(genome_dir, gtf_name)
    cdna_path = os.path.join(genome_dir, cdna_name)
    pep_path = os.path.join(genome_dir, pep_name)

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
    logging.info(f'Extracting {gene_id} from transcriptome.')
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


def build_bowtie_index(
    input_path: str, 
    index_dir: str, 
    index_prefix: str,
    args: str,
    tsl: bool = False, 
    tsl_list: Optional[list] = None, 
    genome: Optional[Genome] = None, 
    gene_only: Optional[bool] = False, 
    gene_id: Optional[str] = None,
    ) -> None:
    """
    Builds a Bowtie2 index for the specified species if not already present.
    
    Parameters:
        input_path (str): Path to the input FASTA file (Must end with .all.fa.gz).
        index_dir (str): Path to the directory where the Bowtie2 index will be saved.
        index_prefix (str): Prefix for the Bowtie2 index files. (e.g., 'GRCh38_113')
        args (str): Additional command-line arguments for Bowtie2.
        tsl (bool, optional): Whether to filter transcripts by transcript support level.
        tsl_list (list, optional): transcript support levels. i.e. [1,2,4,None]. Required if tsl is True.
        genome (Genome, optional): PyEnsembl genome object. Required if tsl is True.
        gene_only (bool, optional): Whether to index only one gene.
        gene_id (str): Gene identifier to extract if gene_only is True.

    
    Returns:
        index_path (str): Path to the Bowtie2 index.
    """

    # TODO: change tsl namings for index

    # Build dynamic log message based on parameters
    log_msg = f"building bowtie index for {index_prefix}"
    if tsl:
        log_msg += f" with tsl active"
    if gene_only:
        log_msg += f" and gene_only active"
    logging.info(log_msg)

    if tsl:
        # Create a new filename for the filtered FASTA
        tsl_input_path = input_path.replace('.all.fa.gz', f'.tsl{"_".join(map(str, tsl_list))}.fa.gz')
        filter_transcripts_by_tsl(input_path, tsl_input_path, genome, tsl_list)
        input_path = tsl_input_path
        index_name = f"{index_prefix}_tsl{'_'.join(map(str, tsl_list))}"
    else:
        index_name = index_prefix
        
    
    if gene_only:
        gene_input_path = input_path.replace('.all.fa.gz', f'.{gene_id}.fa.gz')
        extract_gene(input_path, gene_input_path, gene_id)
        input_path = gene_input_path
        index_name = f"{index_name}_{gene_id}_only"


    try:
        files_in_dir = os.listdir(index_dir)
    except OSError as e:
        logging.error("Error reading directory %s: %s", index_dir, e)
        raise RuntimeError("Error reading directory.") from e
    
    index_path = os.path.join(index_dir, index_name)

    file_exists = any(file.startswith(index_name + ".") for file in files_in_dir)
    if not file_exists:
        command = ["bowtie2-build", input_path, index_path]
        if args:
            command.extend(shlex.split(args))
            
        logging.info("Executing Bowtie2-build command: %s", " ".join(command))
        start_time = time.time()
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            logging.error("Bowtie2-build execution failed: %s", e.stderr.strip())
            raise RuntimeError("Bowtie2-build execution failed.") from e

        elapsed = time.time() - start_time
        logging.info("Bowtie2-build processing time: %.2f seconds", elapsed)

    else:
        logging.info("Using existing index: %s", index_name)

    return index_path

def run_bowtie(
    in_file: str,
    index_path: str,
    bowtie_args: str,
    bowtie2Home: str,
    gene_only: bool = False,
    gene_id: Optional[str] = None,
    trim: bool = False,
    multiplicity_layout: Optional[List[int]] = None,
    ) -> str:
    """
    Execute Bowtie2 alignment for the k-mers.

    Parameters:
        in_file (str): Path to the input file.
        index_path (str): Path to the Bowtie2 index.
        bowtie_args (str): Additional command-line arguments for Bowtie2.
        bowtie2Home (str): Path to the Bowtie2 output directory.
        gene_only (bool): If True, aligns only to the target gene region.
        gene_id (Optional[str]): The gene identifier to use for gene_only alignment. Required if gene_only is True.
        trim (bool): If True, apply trimming options.
        multiplicity_layout (Optional[List[int]]): A sequence containing at least three integers.
            When trim is True, the first and third elements are used for '--trim5' and '--trim3', respectively.

    Returns:
        str: The path to the output SAM file.
    """
    in_file_name = os.path.basename(in_file)
    if gene_only:
        logging.info("Running Bowtie2 alignment for target gene")
        if not gene_id:
            msg = "gene_id must be provided when gene_only is True."
            logging.error(msg)
            raise ValueError(msg)

        out_file_name = f"{os.path.splitext(in_file_name)[0]}_target_only.sam"
    else:
        logging.info("Running Bowtie2 alignment")
        out_file_name = f"{os.path.splitext(in_file_name)[0]}.sam"


    if trim:
        if not multiplicity_layout or len(multiplicity_layout) < 3:
            msg = "When trim is True, multiplicity_layout must contain at least three integers."
            logging.error(msg)
            raise ValueError(msg)
        trim5_val = str(multiplicity_layout[0])
        trim3_val = str(multiplicity_layout[2])
        out_file_name = f"{os.path.splitext(out_file_name)[0]}_trimmed.sam"

    out_file_path = os.path.join(bowtie2Home, out_file_name)

    # Build the initial command as a list to avoid shell injection issues.
    command = ["bowtie2", "-x", index_path, "-U", in_file, "-S", out_file_path]
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
    return out_file_path

    
def build_RNAcofold_in(
    cofold_in: str, 
    targets: Dict[str, TargetSite], 
    # targets: Optional[Dict[str, List[Tuple[Any, str]]]] = None
    ) -> None:
    """
    Builds an input file for RNAcofold analysis from filtered k-mers.
    
    Parameters:
        cofold_in (str): Path to the output file for RNAcofold input.
        kmers (List[Tuple[str, str]]): List of tuples containing k-mer identifier and sequence.
        targets (Optional[Dict[str, List[Tuple[Any, str]]]]): Optional mapping of k-mer identifiers to target sequences.
            If provided, the reverse complement of these target sequences will be used.
    
    Returns:
        None

    """
    logging.info("Building RNAcofold input file")

    with open(cofold_in, "w") as cofold_file:
        # if targets:
        #     for kmer_id, seq in kmers:
        #         if kmer_id in targets:
        #             for i, target in enumerate(targets[kmer_id]):
                        
        #                 # Write header and sequence lines.
        #                 kmer_file.write(f">{kmer_id}_{i}\n")
        #                 kmer_file.write(f"{seq}&{str(Seq(target[1]).reverse_complement())}\n")
        #         else:
        #             logging.warning(f"No target found for k-mer {kmer_id}, skipping targets.")
        # else:
            for key, targetSite in targets.items():
                cofold_file.write(f">{key}\n")
                cofold_file.write(f"{targetSite.sequence}&{str(Seq(targetSite.sequence).reverse_complement())}\n")
    
    logging.info("RNAcofold input file created successfully.")
                
def run_RNAcofold(
    cofold_in_file: str, 
    param_file_path: str
) -> str:
    """
    Run RNAcofold to calculate RNA secondary structure energies and save the results to a CSV file.

    Parameters:
        cofold_in_file (str): Path to the RNA sequences input file for RNAcofold.
        param_file_path (str): Parameter file for RNAcofold.

    Returns:
        str: The path to the output CSV file containing RNAcofold results.
        
    Raises:
        subprocess.CalledProcessError: If RNAcofold returns a non-zero exit code.
    """
    outFile = os.path.splitext(cofold_in_file)[0] + "_cofoldout.csv"
    logging.info("Running RNAcofold")
    
    command = [
        'RNAcofold', 
        '-p0', 
        '-d1', 
        '--output-format=D', 
        '--jobs=0', 
        '--noPS', 
        '--noconv', 
        cofold_in_file, 
        '-P', 
        param_file_path
    ]
    
    logging.info(f"Command: {' '.join(command)}")

    with open(outFile, 'w') as rcfOutFile:
        process = subprocess.Popen(
            command,  # No need for shlex.split as this is already a list
            stdout=rcfOutFile, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        # Read stderr in real time until the process ends
        try:
            for line in process.stderr:
                logging.info(line.strip())
        finally:
            # Ensure stderr is closed
            process.stderr.close()
            
        # Wait for process to complete and check return code
        return_code = process.wait()
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, command)
            
    logging.info(f"RNAcofold completed successfully, output saved to {outFile}")
    return outFile
