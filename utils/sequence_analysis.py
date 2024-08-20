import logging
import multiprocessing
from tqdm import tqdm
import pandas as pd
import configparser
import os
import subprocess
import shlex


# Create a configparser object
config = configparser.ConfigParser()

# Read the configuration file
config.read('config.ini')

def get_chromosomal_positions_per_transcript(transcript, position_in_transcript, ensembl_obj, k, ensembl_obj_scaffolds = None):
    """
    Retrieve the absolute chromosomal positions corresponding to a specific relative position within a transcript.

    This function calculates the chromosomal coordinates for a given position within a transcript.
    It first attempts to find the transcript using the main Ensembl object. If not found, it checks
    within an optional scaffold annotation if provided.

    Parameters:
        transcript (str): The Ensembl transcript ID.
        position_in_transcript (int): The position within the transcript for which chromosomal coordinates are needed.
        ensembl_obj (Genome): The main EnsemblRelease object for querying transcript data.
        ensembl_obj_scaffolds (Genome, optional): An optional Genome object for scaffold annotations.

    Returns:
        str: A string key representing the chromosomal coordinates in the format 
             'contig:start_pos-end_pos:strand', or None if the transcript is not found.
    """
    transcript_id = transcript.split(".")[0]

    try:
        transcript = ensembl_obj.transcript_by_id(transcript_id=transcript_id)
    except Exception as e:
        try:
            transcript = ensembl_obj_scaffolds.transcript_by_id(transcript_id=transcript_id)
        except Exception as e:
            logging.warning(e)
            return None

    start_pos, end_pos = calculate_chromosomal_positions(
        transcript.exon_intervals,
        position_in_transcript,
        transcript.strand,
        k
    )
    
    key = f'{transcript.contig}:{start_pos}-{end_pos}:{transcript.strand}'
    return key

def calculate_chromosomal_positions(exon_intervals, pos, strand, k):
    
    accumulated = 0
    
    exon_intervals = sorted(exon_intervals, key=lambda x: x[0], reverse=True)
    
    if strand == '-':
        
        for exon in exon_intervals:
            if (accumulated + (exon[1] - exon[0] + 1)) > pos:
                start_pos = (exon[1] - (pos - accumulated) + 1 - k)
                return start_pos, start_pos + k
            
            accumulated += (exon[1] - exon[0] + 1)
            
    elif strand == '+':
        
        for exon in reversed(exon_intervals):
            if (accumulated + (exon[1] - exon[0] + 1)) > pos:
                start_pos = (exon[0] + (pos - accumulated) - 1)
                return start_pos, start_pos + k
            
            accumulated += (exon[1] - exon[0] + 1)

def getRNAcofoldEnergy(rnaCofoldInFile):
    """
    Run RNAcofold to calculate RNA secondary structure energies and save the results to a CSV file.

    This function executes the RNAcofold tool to perform RNA secondary structure folding calculations on
    the input RNA sequences file. The results, including the free energy of the fold, are saved to an output 
    CSV file. The function logs the process and any error messages.

    Parameters:
        rnaCofoldInFile (str): The path to the input file containing RNA sequences in the format suitable for RNAcofold.

    Returns:
        str: The path to the output CSV file where the RNAcofold results are saved.
    """
    outFile = os.path.splitext(rnaCofoldInFile)[0] + "_cofold_out.csv"

    
    # Run RNAcofold
    logging.info("Running RNAcofold")
    command = f'RNAcofold -p0  --output-format=D --jobs=0 --noPS --noconv {rnaCofoldInFile} {config["DEFAULT"]["CofoldParamFile"]}'
    logging.info("Command: {}".format(command))
    
    with open(outFile, 'w') as rcfOutFile:
        process = subprocess.Popen(shlex.split(command), stdout=rcfOutFile, stderr=subprocess.PIPE)
        while True:
            output = process.stderr.readline().decode()
            if output == '' and process.poll() is not None:
                break
            if output:
                logging.info(output.strip())
        rc = process.poll()

    return outFile

def get_exon_id(pos_in_transcript, transcript):
    """
    Retrieve the exon ID corresponding to a specific position within a transcript.

    This function determines which exon contains the given position within the transcript sequence. 
    The function processes exons in the correct order depending on the strand orientation to find the 
    exon containing the position.

    Parameters:
        pos_in_transcript (int): The position within the transcript sequence for which the exon ID is needed.
        transcript (Transcript): A transcript object containing exon information and strand orientation.

    Returns:
        str: The exon ID of the exon containing the specified position within the transcript. If no exon 
             contains the position, the function returns None.
    """
    
    accumulated = 0
    
    exons = sorted(transcript.exons, key=lambda x: x.start, reverse=True)
    
    if transcript.strand == '-':
        
        for exon in exons:
            
            if (accumulated + (exon.end - exon.start + 1)) > pos_in_transcript:
                return exon.exon_id
            
            accumulated += (exon.end - exon.start + 1)
            
    elif transcript.strand == '+':
        
        for exon in reversed(exons):
            if (accumulated + (exon.end - exon.start + 1)) > pos_in_transcript:
                return exon.exon_id

            
            accumulated += (exon.end - exon.start + 1)

def gc_content(seq):
    """
    Calculate the GC content of a nucleotide sequence.

    The GC content is the proportion of nucleotides in a sequence that are either guanine (G) or cytosine (C). 
    This function handles mixed cases by converting the sequence to uppercase before performing calculations.

    Parameters:
        seq (str): The nucleotide sequence for which GC content is to be calculated.

    Returns:
        float: The GC content of the sequence as a proportion (0 to 1). The proportion is the number of G and C nucleotides 
               divided by the total length of the sequence.
    """
    # Convert sequence to uppercase to handle mixed cases
    seq = seq.upper()
    
    # Count G and C in the sequence
    g_count = seq.count('G')
    c_count = seq.count('C')
    
    # Calculate GC content as a percentage
    gc_percentage = (g_count + c_count) / len(seq)
    
    return gc_percentage   

def longest_at_run(seq):
    """
    Find the proportion of the longest run of A or T nucleotides in a sequence.

    This function identifies the longest contiguous run of adenine (A) or thymine (T) nucleotides in the sequence 
    and calculates its proportion relative to the total length of the sequence. The sequence is handled in uppercase 
    to account for mixed cases.

    Parameters:
        seq (str): The nucleotide sequence in which to find the longest AT run.

    Returns:
        float: The proportion of the sequence occupied by the longest run of A or T nucleotides. This is the length of the 
               longest AT-run divided by the total length of the sequence.
    """
    # Convert sequence to uppercase to handle mixed cases
    seq = seq.upper()
    
    # Initialize variables for the longest AT-run
    max_at_run = 0
    current_at_run = 0
    
    # Iterate through the sequence
    for nucleotide in seq:
        if nucleotide in 'AT':
            current_at_run += 1
            if current_at_run > max_at_run:
                max_at_run = current_at_run
        else:
            current_at_run = 0  # Reset AT-run counter if not A or T
    
    proportion_at_run = max_at_run / len(seq)

    return proportion_at_run 

def longest_t_run(seq):
    """
    Find the proportion of the longest run of T nucleotides in a sequence.

    This function identifies the longest contiguous run of thymine (T) nucleotides in the sequence 
    and calculates its proportion relative to the total length of the sequence. The sequence is handled in uppercase 
    to account for mixed cases.

    Parameters:
        seq (str): The nucleotide sequence in which to find the longest T run.

    Returns:
        float: The proportion of the sequence occupied by the longest run of T nucleotides. This is the length of the 
               longest T-run divided by the total length of the sequence.
    """
    # Convert sequence to uppercase to handle mixed cases
    seq = seq.upper()
    
    # Initialize variables for the longest T-run
    max_t_run = 0
    current_t_run = 0
    
    # Iterate through the sequence
    for nucleotide in seq:
        if nucleotide == 'T':
            current_t_run += 1
            if current_t_run > max_t_run:
                max_t_run = current_t_run
        else:
            current_t_run = 0  # Reset T-run counter if not T
    
    proportion_t_run = max_t_run / len(seq)

    return proportion_t_run