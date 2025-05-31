import os
import gzip
import shlex
import subprocess
import logging
from typing import Optional, List, Tuple, Dict, Any, Union
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from genome_utils import Genome, TargetSite, Site
import time
import gget
import urllib.request, urllib.parse
from src.utils.time_utils import timed, format_duration




def download_genome(
    species: str,
    e_release: int,
    genome_dir: str,
    ) -> Tuple[str, str, str, str, Optional[str]]:
    """
    Download the genome files for a specified species.
    
    Args:
        species (str): Species name. e.g., 'homo_sapiens'.
        e_release (int): The Ensembl release version.
        genome_dir (str): Path to the directory where the genome files will be saved.
        
    Returns:
        Tuple[str, str, str, str, Optional[str]]: Paths to the GTF, cDNA, peptide, genome FASTA files, and an optional scaffold GTF path.
    """
    gtf_url, cdna_url, pep_url, genome_url = tuple(
        gget.ref(species, which=["gtf", "cdna", "pep", "dna"], release=e_release, ftp=True, verbose=False)
    )

    gtf_name = os.path.basename(urllib.parse.urlparse(gtf_url).path)
    cdna_name = os.path.basename(urllib.parse.urlparse(cdna_url).path)
    genome_name = os.path.basename(urllib.parse.urlparse(genome_url).path)

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
    genome_path = os.path.join(genome_dir, genome_name)

    if not os.path.exists(gtf_path):
        logging.info("Downloading GTF file to '%s'", gtf_path)
        urllib.request.urlretrieve(gtf_url, gtf_path)
    else:
        logging.info("GTF file already exists at '%s'", gtf_path)
        
    if not os.path.exists(cdna_path):
        logging.info("Downloading cDNA file to '%s'", cdna_path)
        urllib.request.urlretrieve(cdna_url, cdna_path)
    else:
        logging.info("cDNA file already exists at '%s'", cdna_path)
        
    if not os.path.exists(genome_path):
        logging.info("Downloading genome FASTA file to '%s'", genome_path)
        urllib.request.urlretrieve(genome_url, genome_path)
    else:
        logging.info("Genome FASTA file already exists at '%s'", genome_path)

    return gtf_path, cdna_path, genome_path, scaffold_gtf_path



def extract_gene(
    fasta_gz_in: str, 
    fasta_gz_out: str, 
    gene_id: str,
    ) -> None:
    """
    Extract a specific gene from a .fa.gz file and save the filtered sequences.
    Skips extraction if the output file already exists.
    """
    if os.path.exists(fasta_gz_out):
        logging.info(f'Output file {fasta_gz_out} already exists. Using existing file.')
        return
        
    logging.info(f'Extracting {gene_id} from transcriptome.')
    try:
        with gzip.open(fasta_gz_in, "rt") as infile, gzip.open(fasta_gz_out, "wt") as outfile:
            sequences = SeqIO.parse(infile, "fasta")
            filtered_sequences = (seq for seq in sequences if gene_id in seq.description)
            SeqIO.write(filtered_sequences, outfile, "fasta")
    except OSError as e:
        logging.error("Error processing gene extraction files: %s", e)
        raise


def _filter_transcripts_by_tsl(
    fasta_gz_in: str,
    fasta_gz_out: str,
    genome: Genome,
    tsl_list: List[Optional[int]],
    ) -> None:
    """
    Filter transcripts from a gzipped FASTA file based on transcript support levels using the
    genome object for transcript details. The filtered sequences are written to a gzipped FASTA file.
    Skips filtering if the output file already exists.
    
    Args:
        fasta_gz_in (str): Path to the input gzipped FASTA file containing transcript records.
        fasta_gz_out (str): Path to the output gzipped FASTA file.
        genome (Genome): Genome object that provides transcript details via a transcripts() method.
        tsl_list (List[Optional[int]]): List of allowed transcript support level values (e.g., [1, 2, 3, None]).
    """
    if os.path.exists(fasta_gz_out):
        logging.info(f'Output file {fasta_gz_out} already exists. Using existing file.')
        return
    
    logging.info("Filtering %s for transcript support levels: %s", genome.reference_name, tsl_list)

    tsl_set = set(tsl_list)

    transcript_to_gene = {}
    for t in genome.transcripts():
        if t.support_level in tsl_set:
            transcript_to_gene[t.transcript_id] = t.gene_id
    
    batch_size = 1000
    
    with gzip.open(fasta_gz_in, "rt") as infile, gzip.open(fasta_gz_out, "wt") as outfile:
        batch = []
        for seq in SeqIO.parse(infile, "fasta"):
            transcript_id = seq.id.split('.')[0]
            if transcript_id in transcript_to_gene:
                new_record = SeqRecord(
                    seq.seq,
                    id=seq.id,
                    description=transcript_to_gene[transcript_id]
                )
                batch.append(new_record)
                
                if len(batch) >= batch_size:
                    SeqIO.write(batch, outfile, "fasta")
                    batch = []
        
        if batch:
            SeqIO.write(batch, outfile, "fasta")
        
    logging.info("Transcript filtering completed.")


def _build_bowtie_index(
    input_path: str, 
    index_dir: str, 
    index_prefix: str,
    args: str = "",
    tsl: bool = False, 
    tsl_list: Optional[list] = None, 
    genome: Optional[Genome] = None, 
    gene_only: Optional[bool] = False, 
    gene_id: Optional[str] = None,
    ) -> str:
    """
    Builds a Bowtie2 index for the specified input file if not already present.
    
    Parameters:
        input_path (str): Path to the input FASTA file.
        index_dir (str): Path to the directory where the Bowtie2 index will be saved.
        index_prefix (str): Prefix for the Bowtie2 index files. (e.g., 'GRCh38_113')
        args (str): Additional command-line arguments for Bowtie2.
        tsl (bool, optional): Whether to filter transcripts by transcript support level.
        tsl_list (list, optional): transcript support levels. i.e. [1,2,4,None]. Required if tsl is True.
        genome (Genome, optional): genome object. Required if tsl is True.
        gene_only (bool, optional): Whether to index only one gene.
        gene_id (str): Gene identifier to extract if gene_only is True.
    
    Returns:
        str: Path to the Bowtie2 index.
    """
    log_msg = f"Building Bowtie index for {index_prefix}"
    if tsl:
        log_msg += f" with TSL filtering"
    if gene_only:
        log_msg += f" for gene {gene_id} only"
    logging.info(log_msg)

    index_name = index_prefix
    if tsl:
        tsl_suffix = f"_tsl{'_'.join(map(str, tsl_list))}"
        index_name += tsl_suffix
    if gene_only:
        index_name += f"_{gene_id}_only"

    modified_input_path = input_path
    if tsl:
        tsl_input_path = input_path.replace('all.fa.gz', f'{tsl_suffix}.fa.gz')
        
        if os.path.exists(tsl_input_path):
            logging.info(f"Using existing TSL-filtered file: {tsl_input_path}")
        else:
            logging.info(f"Creating TSL-filtered file: {tsl_input_path}")
            _filter_transcripts_by_tsl(input_path, tsl_input_path, genome, tsl_list)
            
        modified_input_path = tsl_input_path
    
    if gene_only:
        gene_input_path = modified_input_path.replace('.fa.gz', f'.{gene_id}.fa.gz')
        
        if os.path.exists(gene_input_path):
            logging.info(f"Using existing gene-specific file: {gene_input_path}")
        else:
            logging.info(f"Creating gene-specific file: {gene_input_path}")
            extract_gene(modified_input_path, gene_input_path, gene_id)
            
        modified_input_path = gene_input_path

    try:
        files_in_dir = os.listdir(index_dir)
    except OSError as e:
        logging.error("Error reading directory %s: %s", index_dir, e)
        raise RuntimeError("Error reading directory.") from e
    
    index_path = os.path.join(index_dir, index_name)
    file_exists = any(file.startswith(index_name + ".") for file in files_in_dir)
    
    if not file_exists:
        if not os.path.exists(modified_input_path):
            logging.error(f"Input file does not exist: {modified_input_path}")
            raise FileNotFoundError(f"Input file not found: {modified_input_path}")
            
        command = ["bowtie2-build", modified_input_path, index_path]
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



def build_transcriptomic_bowtie_index(
    input_path: str, 
    index_dir: str, 
    index_prefix: str,
    args: str = "",
    tsl: bool = False, 
    tsl_list: Optional[list] = None, 
    genome: Optional[Genome] = None, 
    gene_only: Optional[bool] = False, 
    gene_id: Optional[str] = None,
    ) -> str:
    """
    Builds a Bowtie2 index for transcriptomic data.
    
    Parameters:
        input_path (str): Path to the input transcriptome FASTA file (Must end with .all.fa.gz).
        index_dir (str): Path to the directory where the Bowtie2 index will be saved.
        index_prefix (str): Prefix for the Bowtie2 index files. (e.g., 'GRCh38_113')
        args (str): Additional command-line arguments for Bowtie2.
        tsl (bool, optional): Whether to filter transcripts by transcript support level.
        tsl_list (list, optional): transcript support levels. i.e. [1,2,4,None]. Required if tsl is True.
        genome (Genome, optional): PyEnsembl genome object. Required if tsl is True.
        gene_only (bool, optional): Whether to index only one gene.
        gene_id (str): Gene identifier to extract if gene_only is True.
    
    Returns:
        str: Path to the Bowtie2 index.
    """
    if not input_path.endswith('.all.fa.gz'):
        logging.warning("Transcriptomic input file should typically end with '.all.fa.gz'")
    
    return _build_bowtie_index(
        input_path=input_path,
        index_dir=index_dir,
        index_prefix=index_prefix,
        args=args,
        tsl=tsl,
        tsl_list=tsl_list,
        genome=genome,
        gene_only=gene_only,
        gene_id=gene_id
    )


def build_genomic_bowtie_index(
    input_path: str, 
    index_dir: str, 
    index_prefix: str,
    args: str = "",
    ) -> str:
    """
    Builds a Bowtie2 index for genomic data.
    
    Parameters:
        input_path (str): Path to the input genome FASTA file.
        index_dir (str): Path to the directory where the Bowtie2 index will be saved.
        index_prefix (str): Prefix for the Bowtie2 index files. (e.g., 'GRCh38')
        args (str): Additional command-line arguments for Bowtie2.
    
    Returns:
        str: Path to the Bowtie2 index.
    """
    genomic_prefix = f"{index_prefix}_genomic"
    
    return _build_bowtie_index(
        input_path=input_path,
        index_dir=index_dir,
        index_prefix=genomic_prefix,
        args=args,
        tsl=False,
        gene_only=False
    )


def create_job_config_summary(job_dir: str, config: dict) -> None:
    """
    Create a summary file containing all configuration parameters used for the job.
    
    Parameters:
        job_dir (str): Path to the job directory
        config (dict): Dictionary containing all configuration parameters
    """
    config_file = os.path.join(job_dir, 'job_config.txt')
    
    with open(config_file, 'w') as f:
        f.write("Job Configuration Summary\n")
        f.write("=======================\n\n")
        f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        for key, value in config.items():
            f.write(f"{key}: {value}\n")
            
    logging.info(f"Job configuration summary written to {config_file}")


@timed
def run_bowtie(
    infile_path: str,
    index_path: str,
    bowtie_args: str,
    trim: bool = False,
    multiplicity_layout: Optional[List[int]] = None,
) -> str:
    """
    Run Bowtie2 alignment on the input file.
    
    Args:
        infile_path (str): Path to input FASTA file
        index_path (str): Path to Bowtie2 index
        bowtie_args (str): Additional Bowtie2 arguments
        trim (bool): Whether to trim the input sequences
        multiplicity_layout (List[int]): Layout for multiplicity calculation
        
    Returns:
        str: Path to output SAM file
    """
    infile_name = os.path.splitext(os.path.basename(infile_path))[0]
    const_args = ["--no-head", "-t", "-N 0", "-a", "-f", "--norc", "--no-unal"]
    
    if trim:
        if not multiplicity_layout or len(multiplicity_layout) < 3:
            msg = "When trim is True, multiplicity_layout must contain at least three integers."
            logging.error(msg)
            raise ValueError(msg)
        trim5_val = str(multiplicity_layout[0])
        trim3_val = str(multiplicity_layout[2])
        infile_name = f"{infile_name}_trimmed"
        
    index_name = os.path.splitext(os.path.basename(index_path))[0]
    
    job_dir = os.path.dirname(os.path.dirname(infile_path))
    bowtie_outputs_dir = os.path.join(job_dir, 'bowtie2')
    os.makedirs(bowtie_outputs_dir, exist_ok=True)
    
    out_file_name = f"{infile_name}_on_{index_name}.sam"
    out_file_path = os.path.join(bowtie_outputs_dir, out_file_name)
    
    command = ["bowtie2", "-x", index_path, "-U", infile_path, "-S", out_file_path]
    command.extend(const_args)
    
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
    logging.info(f"Bowtie2 processing completed in {format_duration(elapsed)}")
    
    return out_file_path


def _build_kmc_index(
    input_path: str,
    index_dir: str,
    index_prefix: str,
    args: str = "",
    k: Optional[int] = None,
    count_min: Optional[int] = None
) -> str:
    """
    Builds a kmc index for the specified input file if not already present.

    Parameters:
        input_path (str): Path to the input FASTA file.
        index_dir (str): Path to the directory where the kmc index will be saved.
        index_prefix (str): Prefix for the kmc index files.
        args (str): Additional command-line arguments for kmc (e.g., "-t4 -m12" to set threads and memory).
        k (Optional[int]): K-mer size. If None, kmc default might be used or it might require it.
        count_min (Optional[int]): Minimum k-mer count threshold (kmc's -ci option). If None, kmc default (usually 1).

    Returns:
        str: Path to the kmc index prefix.
    """
    logging.info(f"Building kmc index for {index_prefix} with k={k}, count_min={count_min}")

    # Modify index_prefix to include k and count_min if they are set
    current_index_prefix = index_prefix
    if k is not None:
        current_index_prefix += f"_k{k}"
    if count_min is not None:
        current_index_prefix += f"_ci{count_min}"

    os.makedirs(index_dir, exist_ok=True)
    index_path_prefix = os.path.join(index_dir, current_index_prefix)

    # kmc creates two files: index_prefix.kmc_pre and index_prefix.kmc_suf
    kmc_pre_file = f"{index_path_prefix}.kmc_pre"
    kmc_suf_file = f"{index_path_prefix}.kmc_suf"

    if not (os.path.exists(kmc_pre_file) and os.path.exists(kmc_suf_file)):
        if not os.path.exists(input_path):
            logging.error(f"Input file does not exist: {input_path}")
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Basic kmc command structure: kmc [options] <input_file_name> <output_file_name> <working_directory>
        # We will use the @file_list option for input if needed, but for a single file, it's direct.
        # Output_file_name is the prefix.
        command = [
            "kmc",
            # Threads and memory should be passed via 'args' if needed, e.g., args="-t4 -m12"
        ]
        if k is not None:
            command.append(f"-k{k}")
        if count_min is not None:
            command.append(f"-ci{count_min}")

        if args:
            command.extend(shlex.split(args)) # Ensure args are correctly parsed

        command.extend([input_path, index_path_prefix, index_dir])

        logging.info("Executing kmc command: %s", " ".join(command))
        start_time = time.time()
        try:
            process = subprocess.run(command, check=True, capture_output=True, text=True)
            if process.stdout:
                logging.info("kmc STDOUT: %s", process.stdout.strip())
            if process.stderr: # kmc often uses stderr for progress/info
                logging.info("kmc STDERR: %s", process.stderr.strip())
        except subprocess.CalledProcessError as e:
            logging.error("kmc execution failed. RC: %s", e.returncode)
            if e.stdout:
                logging.error("kmc STDOUT: %s", e.stdout.strip())
            if e.stderr:
                logging.error("kmc STDERR: %s", e.stderr.strip())
            raise RuntimeError("kmc execution failed.") from e

        elapsed = time.time() - start_time
        logging.info("kmc index building time: %.2f seconds", elapsed)
    else:
        logging.info("Using existing kmc index: %s", current_index_prefix)

    return index_path_prefix


def build_genomic_kmc_index(
    input_path: str,
    index_dir: str,
    index_prefix: str,
    args: str = "",
    k: Optional[int] = None,
    count_min: Optional[int] = None
) -> str:
    """
    Builds a kmc index for genomic data.

    Parameters:
        input_path (str): Path to the input genome FASTA file.
        index_dir (str): Path to the directory where the kmc index will be saved.
        index_prefix (str): Prefix for the kmc index files (e.g., 'GRCh38_genomic').
        args (str): Additional command-line arguments for kmc (e.g., "-cs1000 -t4 -m12").
                    It's crucial to pass k-mer size (-k) and count-min (-ci) or other relevant kmc params here if not using dedicated params.
                    Threads and memory can also be specified here (e.g. -t<threads> -m<memory_in_GB>).
        k (Optional[int]): K-mer size. If None, it's recommended to set it explicitly.
        count_min (Optional[int]): Minimum k-mer count threshold. If None, kmc default (usually 1).

    Returns:
        str: Path to the kmc index prefix.
    """
    genomic_kmc_prefix = f"{index_prefix}_kmc"

    return _build_kmc_index(
        input_path=input_path,
        index_dir=index_dir,
        index_prefix=genomic_kmc_prefix,
        args=args,
        k=k,
        count_min=count_min
    )


def build_RNAcofold_in(
    cofold_in: str, 
    targets: Union[Dict[str, TargetSite], Dict[str, List[Site]]],
    reference_targets: Optional[Dict[str, TargetSite]] = None
) -> None:
    """
    Builds an input file for RNAcofold analysis for either self-folding or secondary binding.
    
    Parameters:
        cofold_in (str): Path to the output file for RNAcofold input.
        targets: Either:
            - Dict[str, TargetSite]: For self-folding analysis (sequence with its own reverse complement)
            - Dict[str, List[Site]]: For secondary sites analysis (comparing reference to potential 
              secondary sites)
        reference_targets: Optional[Dict[str, TargetSite]]: When using the second mode (list of TargetSites),
            this provides the reference sequences to compare the corresponding oligo (reverse complement) to the secondary sites. If None, the function will expect the
            first mode (self-folding).
    
    Returns:
        None
    """
    logging.info("Building RNAcofold input file")
    entry_count = 0
    
    os.makedirs(os.path.dirname(cofold_in), exist_ok=True)
    
    with open(cofold_in, "w") as cofold_file:
        if targets and isinstance(next(iter(targets.values())), list):
            if not reference_targets:
                raise ValueError("reference_targets must be provided when targets contains lists of TargetSites")
            
            for target_id, secondary_sites in targets.items():
                if target_id not in reference_targets:
                    logging.warning(f"No reference target found for {target_id}, skipping")
                    continue
                    
                reference_seq = reference_targets[target_id].sequence
                
                for i, secondary_site in enumerate(secondary_sites):
                    entry_id = f"{target_id}_{i}"
                    
                    cofold_file.write(f">{entry_id}\n")
                    cofold_file.write(f"{secondary_site.sequence}&{str(Seq(reference_seq).reverse_complement())}\n")
                    entry_count += 1
        else:
            for key, target_site in targets.items():
                cofold_file.write(f">{key}\n")
                cofold_file.write(f"{target_site.sequence}&{str(Seq(target_site.sequence).reverse_complement())}\n")
                entry_count += 1
    
    logging.info(f"RNAcofold input file created successfully with {entry_count} entries")


                
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
    
    os.makedirs(os.path.dirname(outFile), exist_ok=True)
    
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
            command,
            stdout=rcfOutFile, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        try:
            for line in process.stderr:
                logging.info(line.strip())
        finally:
            process.stderr.close()
            
        return_code = process.wait()
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, command)
            
    logging.info(f"RNAcofold completed successfully, output saved to {outFile}")
    return outFile
