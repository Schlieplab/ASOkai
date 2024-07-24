import os
from ftplib import FTP
import subprocess
import shlex
import configparser 
import logging


# Create a configparser object
config = configparser.ConfigParser()

# Read the configuration file
config.read('config.ini')


def collect_scaffold(path, genome_assembly, ensembl_release):
    """
    Download the specified human scaffold file from Ensembl if it is not already present
    in the specified directory. In either case, return the file path to the scaffold.

    This function checks for the presence of the scaffold file in the specified directory.
    If the file does not exist, it connects to the Ensembl FTP server, navigates to the
    appropriate directory, and downloads the scaffold file. If the file already exists,
    it skips the download and returns the path to the existing file.

    Parameters:
        path (str): The base directory path where the scaffold file should be stored.
        genome_assembly (int): The genome assembly version (e.g., 38).
        ensembl_release (int): The Ensembl release version (e.g., 101).

    Returns:
        str: The file path to the scaffold file. If the download fails, it returns None.

    Logs:
    - Prints messages indicating whether the scaffold file was downloaded or an existing file is being used.
    - Prints an error message if the download fails.
    """
        
    filepath = path + f"/pyensembl/GRCh{genome_assembly}/ensembl{ensembl_release}/"
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

def build_bowtie_index(e_release, g_assembly, species, bowtie_index):
    """
    Builds a Bowtie2 index for the specified species using the given Ensembl release and genome assembly.

    Parameters:
        e_release (str): The Ensembl release version.
        g_assembly (str): The genome assembly version.
        species (str): The species for which the index is being built. Valid values are 'human' and 'mouse'.
        bowtie_index (str): The name of the Bowtie2 index to be created.

    Returns:
        int: The return code from the Bowtie2 index build command. A return code of 0 indicates success.
    
    Logs:
    - The function logs the start of the Bowtie2 index build process.
    - The exact command used for building the Bowtie2 index.
    - The return code of the Bowtie2 index build command.
    """
    
    logging.info("Running Bowtie2 index build")

    if species == 'human':
        command = f'bowtie2-build {config["DEFAULT"]["DataDir"]}/pyensembl/GRCh{g_assembly}/ensembl{e_release}/Homo_sapiens.GRCh{g_assembly}.cdna.all.fa.gz {config["DEFAULT"]["DataDir"]}/bowtie2Home/{bowtie_index} {config["DEFAULT"]["BowtieBuildIndexArg"]}'
    elif species == 'mouse':
        command = f'bowtie2-build {config["DEFAULT"]["DataDir"]}/pyensembl/GRCm{g_assembly}/ensembl{e_release}/Mus_musculus.GRCm{g_assembly}.cdna.all.fa.gz {config["DEFAULT"]["DataDir"]}/bowtie2Home/{bowtie_index} {config["DEFAULT"]["BowtieBuildIndexArg"]}'
    
    logging.info("Command: {}".format(command))

        
    return_code = subprocess.call(shlex.split(command))
    logging.info("Return Code: {}".format(return_code))

    return return_code
