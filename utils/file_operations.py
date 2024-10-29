import os
from ftplib import FTP
import subprocess
import shlex
import configparser 
import logging
import gzip
from Bio import SeqIO
from Bio.Seq import Seq



# Create a configparser object
config = configparser.ConfigParser()

# Read the configuration file
config.read('config.ini')


def collect_scaffold(genome_assembly, ensembl_release):
    """
    Download the specified human scaffold file from Ensembl if it is not already present
    in the specified directory. In either case, return the file path to the scaffold.

    This function checks for the presence of the scaffold file in the specified directory.
    If the file does not exist, it connects to the Ensembl FTP server, navigates to the
    appropriate directory, and downloads the scaffold file. If the file already exists,
    it skips the download and returns the path to the existing file.

    Parameters:
        genome_assembly (int): The genome assembly version (e.g., 38).
        ensembl_release (int): The Ensembl release version (e.g., 101).

    Returns:
        str: The file path to the scaffold file. If the download fails, it returns None.

    Logs:
    - Prints messages indicating whether the scaffold file was downloaded or an existing file is being used.
    - Prints an error message if the download fails.
    """
        
    filepath = config['DEFAULT']['PyEnsemblDataDir'] + f"/pyensembl/GRCh{genome_assembly}/ensembl{ensembl_release}/"
    filename = f"Homo_sapiens.GRCh{genome_assembly}.{ensembl_release}.chr_patch_hapl_scaff.gtf.gz"

    if not os.path.exists(filepath+filename):  # Don't re-download.
        ftp = FTP('ftp.ensembl.org')
        ftp.login()
        ftp.cwd(f'pub/release-{ensembl_release}/gtf/homo_sapiens')
        
        os.makedirs(filepath, exist_ok=True)

        with open(filepath + filename, 'wb') as fp:
            
            try:
                ftp.retrbinary("RETR " + filename, fp.write)
            except:
                logging.error('Could not collect Scaffold')
                return None
            
            logging.info(f'Downloaded {filename} Scaffold')
    else:
        logging.info(f'Using {filename} Scaffold')
    return filepath + filename

def build_bowtie_index(e_release, g_assembly, species, bowtie_index_name, gene_id, gene_only = False):
    """
    Builds a Bowtie2 index for the specified species if it is not already present
    in the data directory using the given Ensembl release and genome assembly.

    Parameters:
        e_release (str): The Ensembl release version.
        g_assembly (str): The genome assembly version.
        species (str): The species for which the index is being built. Valid values are 'human' and 'mouse'.
        bowtie_index (str): The name of the Bowtie2 index to be created.
        gene_only (bool): Whether to index only the gene

    Returns:
        int: The return code from the Bowtie2 index build command. A return code of 0 indicates success.
    
    Logs:
    - The function logs the start of the Bowtie2 index build process.
    - The exact command used for building the Bowtie2 index.
    - The return code of the Bowtie2 index build command.
    """

    def extract_gene(fasta_gz_in, fasta_gz_out, gene_to_extract):
        """Extract only a gene from a .fa.gz file and save the result."""
        with gzip.open(fasta_gz_in, "rt") as infile, gzip.open(fasta_gz_out, "wt") as outfile:
            # Filter sequences and write them to the output file
            sequences = SeqIO.parse(infile, "fasta")
            filtered_sequences = (seq for seq in sequences if gene_to_extract in seq.description)
            SeqIO.write(filtered_sequences, outfile, "fasta")
                
                
    logging.info("Running Bowtie2 index build")
    
    if species == 'human':
        cdna_file = f'{config["DEFAULT"]["PyEnsemblDataDir"]}/pyensembl/GRCh{g_assembly}/ensembl{e_release}/Homo_sapiens.GRCh{g_assembly}.cdna.all.fa.gz'
        local_file = f'{config["DEFAULT"]["PyEnsemblDataDir"]}/pyensembl/GRCh{g_assembly}/ensembl{e_release}/Homo_sapiens.GRCh{g_assembly}.cdna.{gene_id}_only.fa.gz'
    elif species == 'mouse':
        cdna_file = f'{config["DEFAULT"]["PyEnsemblDataDir"]}/pyensembl/GRCm{g_assembly}/ensembl{e_release}/Mus_musculus.GRCm{g_assembly}.cdna.all.fa.gz'
        local_file = f'{config["DEFAULT"]["PyEnsemblDataDir"]}/pyensembl/GRCm{g_assembly}/ensembl{e_release}/Mus_musculus.GRCm{g_assembly}.cdna.{gene_id}_only.fa.gz'

    if gene_only:
        bowtie_index_name = bowtie_index_name + '_' + gene_id + '_only'
        extract_gene(cdna_file, local_file, gene_id)
        
    file_exists = False
    for file in os.listdir(f"{config['DEFAULT']['DataDir']}/bowtie2Home/"):
        
        if file.startswith(bowtie_index_name + "."):
            file_exists = True
            break
        
    if not file_exists:  # Don't re-download.
        command = f'bowtie2-build {local_file if gene_only else cdna_file} {config["DEFAULT"]["DataDir"]}/bowtie2Home/{bowtie_index_name} {config["DEFAULT"]["BowtieBuildIndexArg"]}'
    
        logging.info("Command: {}".format(command))
        return_code = subprocess.call(shlex.split(command))
        logging.info("Return Code: {}".format(return_code))
    
    else:
        logging.info(f'Using {bowtie_index_name} as index')
        return 0
        


    return return_code

def build_cofold_in(cofold_in, kmers, targets = None):
    """
    Build an input file for RNAcofold analysis from filtered k-mers.

    This function creates a file in a FASTA-like format suitable for RNAcofold analysis.
    Each k-mer is written as two lines: a header line with the k-mer identifier, and
    a sequence line containing the k-mer sequence and either its reverse complement 
    or a reverse complement of a target sequence if specified.

    Parameters:
    cofold_in (str): The path to the output file where the RNAcofold input will be written.
    kmers (list): A list of tuples, where each tuple contains:
                  - k-mer identifier (str)
                  - k-mer sequence (str)
    targets (dict, optional): A dictionary mapping k-mer identifiers to a list of target sequences (in second index for each target sequence).
                              If provided, the reverse complement of each target sequence will be used
                              instead of the k-mer reverse complement.

    Returns:
    None

    Example:
    >>> kmers = [('S000001', 'ATCG'), ('S000002', 'GCTA')]
    >>> targets = {'S000001': [(_, 'GGTT'), (_, 'AACC')], 'S000002': [(_, 'TTAA')]}
    >>> build_cofold_in('/path/to/cofold_input.txt', kmers, targets)
    """

    directory = os.path.dirname(cofold_in)
    os.makedirs(directory, exist_ok=True)
    
    
    with open(cofold_in, "w") as filteredkmerfile:
        
        if targets:
            for x in kmers:
                for i, y in enumerate(targets[x[0]]):
                    # First line: '>kmer' (where x[0] is the kmer identifier)
                    filteredkmerfile.write('>' + x[0] + '_' + str(i) + '\n')
                    
                    # Second line: 'kmer&reverse_complement'
                    filteredkmerfile.write(x[1] + '&' + str(Seq(y[1]).reverse_complement()) + '\n')
        else:
            for x in kmers:
                # First line: '>kmer' (where x[0] is the kmer identifier)
                filteredkmerfile.write('>' + x[0] + '\n')
                
                # Second line: 'kmer&reverse_complement'
                filteredkmerfile.write(x[1] + '&' + str(Seq(x[1]).reverse_complement()) + '\n')