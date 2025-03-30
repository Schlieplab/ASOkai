import os
import gzip
import shlex
import subprocess
import logging
from typing import Optional, List, Tuple, Dict, Any, Union
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from src.oligo_extractor import TargetSite, Site
from src.utils.genome import Genome
import time
import gget
import urllib.request, urllib.parse




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
    # Retrieve the file URLs from gget.ref
    gtf_url, cdna_url, pep_url, genome_url = tuple(
        gget.ref(species, which=["gtf", "cdna", "pep", "dna"], release=e_release, ftp=True)
    )

    gtf_name = os.path.basename(urllib.parse.urlparse(gtf_url).path)
    cdna_name = os.path.basename(urllib.parse.urlparse(cdna_url).path)
    pep_name = os.path.basename(urllib.parse.urlparse(pep_url).path)
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
    pep_path = os.path.join(genome_dir, pep_name)
    genome_path = os.path.join(genome_dir, genome_name)

    # Download each file (if not already present)
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
        
    if not os.path.exists(pep_path):
        logging.info("Downloading peptide file to '%s'", pep_path)
        urllib.request.urlretrieve(pep_url, pep_path)
    else:
        logging.info("Peptide file already exists at '%s'", pep_path)
        
    if not os.path.exists(genome_path):
        logging.info("Downloading genome FASTA file to '%s'", genome_path)
        urllib.request.urlretrieve(genome_url, genome_path)
    else:
        logging.info("Genome FASTA file already exists at '%s'", genome_path)

    # Return the file paths (including our scaffold_gtf_path)
    return gtf_path, cdna_path, pep_path, genome_path, scaffold_gtf_path



def extract_gene(
    fasta_gz_in: str, 
    fasta_gz_out: str, 
    gene_id: str,
    ) -> None:
    """
    Extract a specific gene from a .fa.gz file and save the filtered sequences.
    Skips extraction if the output file already exists.
    """
    # Check if output file already exists
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
    # Check if output file already exists
    if os.path.exists(fasta_gz_out):
        logging.info(f'Output file {fasta_gz_out} already exists. Using existing file.')
        return
    
    logging.info("Filtering %s for transcript support levels: %s", genome.reference_name, tsl_list)

    tsl_set = set(tsl_list)

    transcript_to_gene = {}
    for t in genome.transcripts():
        if t.support_level in tsl_set:
            transcript_to_gene[t.transcript_id] = t.gene_id
    
    # Process in batches to reduce the number of write operations
    batch_size = 1000
    
    with gzip.open(fasta_gz_in, "rt") as infile, gzip.open(fasta_gz_out, "wt") as outfile:
        batch = []
        for seq in SeqIO.parse(infile, "fasta") :
            transcript_id = seq.id.split('.')[0]
            if transcript_id in transcript_to_gene:
                # Create a new SeqRecord with just the gene name as the description
                # This will result in a FASTA header like ">seq.id gene_id"
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
    # Build dynamic log message based on parameters
    log_msg = f"Building Bowtie index for {index_prefix}"
    if tsl:
        log_msg += f" with TSL filtering"
    if gene_only:
        log_msg += f" for gene {gene_id} only"
    logging.info(log_msg)

    # Determine the final index name based on parameters
    index_name = index_prefix
    if tsl:
        tsl_suffix = f"_tsl{'_'.join(map(str, tsl_list))}"
        index_name += tsl_suffix
    if gene_only:
        index_name += f"_{gene_id}_only"

    # Prepare the input file based on filtering parameters
    modified_input_path = input_path
    if tsl:
        tsl_input_path = input_path.replace('.fa.gz', f'{tsl_suffix}.fa.gz')
        
        # Check if the TSL-filtered file already exists
        if os.path.exists(tsl_input_path):
            logging.info(f"Using existing TSL-filtered file: {tsl_input_path}")
        else:
            logging.info(f"Creating TSL-filtered file: {tsl_input_path}")
            _filter_transcripts_by_tsl(input_path, tsl_input_path, genome, tsl_list)
            
        modified_input_path = tsl_input_path
    
    if gene_only:
        gene_input_path = modified_input_path.replace('.fa.gz', f'.{gene_id}.fa.gz')
        
        # Check if the gene-specific file already exists
        if os.path.exists(gene_input_path):
            logging.info(f"Using existing gene-specific file: {gene_input_path}")
        else:
            logging.info(f"Creating gene-specific file: {gene_input_path}")
            extract_gene(modified_input_path, gene_input_path, gene_id)
            
        modified_input_path = gene_input_path

    # Check if index already exists
    try:
        files_in_dir = os.listdir(index_dir)
    except OSError as e:
        logging.error("Error reading directory %s: %s", index_dir, e)
        raise RuntimeError("Error reading directory.") from e
    
    index_path = os.path.join(index_dir, index_name)
    file_exists = any(file.startswith(index_name + ".") for file in files_in_dir)
    
    if not file_exists:
        # Verify that the modified input file exists before proceeding
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
    
    # Add transcriptomic prefix to index name
    transcriptomic_prefix = f"{index_prefix}_transcriptomic"
    
    return _build_bowtie_index(
        input_path=input_path,
        index_dir=index_dir,
        index_prefix=transcriptomic_prefix,
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
    # Add genomic prefix to index name
    genomic_prefix = f"{index_prefix}_genomic"
    
    return _build_bowtie_index(
        input_path=input_path,
        index_dir=index_dir,
        index_prefix=genomic_prefix,
        args=args,
        tsl=False,
        gene_only=False
    )


def run_bowtie(
    infile_path: str,
    index_path: str,
    bowtie_args: str,
    bowtie2Home: str,
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
        trim (bool): If True, apply trimming options.
        multiplicity_layout (Optional[List[int]]): A sequence containing at least three integers.
            When trim is True, the first and third elements are used for '--trim5' and '--trim3', respectively.

    Returns:
        str: The path to the output SAM file.
    """
    infile_name = os.path.splitext(os.path.basename(infile_path))[0]
    
    
    if trim:
        if not multiplicity_layout or len(multiplicity_layout) < 3:
            msg = "When trim is True, multiplicity_layout must contain at least three integers."
            logging.error(msg)
            raise ValueError(msg)
        trim5_val = str(multiplicity_layout[0])
        trim3_val = str(multiplicity_layout[2])
        infile_name = f"{infile_name}_trimmed"
        
    index_name = os.path.splitext(os.path.basename(index_path))[0]
    
    out_file_name = f"{infile_name}_on_{index_name}.sam"



    out_file_path = os.path.join(bowtie2Home, out_file_name)

    if os.path.exists(out_file_path):
        logging.info("Using existing bowtie2 output: %s", out_file_path)
        return out_file_path
    
    # Build the initial command as a list to avoid shell injection issues.
    command = ["bowtie2", "-x", index_path, "-U", infile_path, "-S", out_file_path]
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
    
    with open(cofold_in, "w") as cofold_file:
        # Determine which mode we're in by checking the first value's type
        if targets and isinstance(next(iter(targets.values())), list):
            # Secondary binding analysis mode
            if not reference_targets:
                raise ValueError("reference_targets must be provided when targets contains lists of TargetSites")
            
            for target_id, secondary_sites in targets.items():
                if target_id not in reference_targets:
                    logging.warning(f"No reference target found for {target_id}, skipping")
                    continue
                    
                reference_seq = reference_targets[target_id].sequence
                
                # Write comparison between reference target and each potential secondary site
                for i, secondary_site in enumerate(secondary_sites):
                    # Create a unique identifier for this comparison
                    entry_id = f"{target_id}_{i}"
                    
                    cofold_file.write(f">{entry_id}\n")
                    cofold_file.write(f"{secondary_site.sequence}&{str(Seq(reference_seq).reverse_complement())}\n")
                    entry_count += 1
        else:
            # Standard self-folding mode
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
