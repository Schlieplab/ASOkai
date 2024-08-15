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

def get_chromosomal_positions_per_transcript(transcript, position_in_transcript, ensembl_obj, ensembl_obj_scaffolds = None):
    transcript_id = transcript.split(".")[0]

    try:
        transcript = ensembl_obj.transcript_by_id(transcript_id=transcript_id)
    except Exception as e:
        try:
            transcript = ensembl_obj_scaffolds.transcript_by_id(transcript_id=transcript_id)
        except Exception as e:
            logging.warning(e)
            return

    start_pos, end_pos = calculate_chromosomal_positions(
        transcript.exon_intervals,
        position_in_transcript,
        transcript.strand
    )
    
    key = f'{transcript.contig}:{start_pos}-{end_pos}:{transcript.strand}'
    return key

def calculate_chromosomal_positions(exon_intervals, pos, strand):
    
    accumulated = 0
    
    exon_intervals = sorted(exon_intervals, key=lambda x: x[0], reverse=True)
    
    if strand == '-':
        
        for exon in exon_intervals:
            if (accumulated + (exon[1] - exon[0] + 1)) > pos:
                start_pos = (exon[1] - (pos - accumulated) + 1 - 16)
                return start_pos, start_pos + 16
            
            accumulated += (exon[1] - exon[0] + 1)
            
    elif strand == '+':
        
        for exon in reversed(exon_intervals):
            if (accumulated + (exon[1] - exon[0] + 1)) > pos:
                start_pos = (exon[0] + (pos - accumulated) - 1)
                return start_pos, start_pos + 16
            
            accumulated += (exon[1] - exon[0] + 1)

def getRNAcofoldEnergy(rnaCofoldInFile):
    rcfOutFileName = os.path.splitext(rnaCofoldInFile)[0] + ".rnacofoldout"
    outFile = os.path.splitext(rnaCofoldInFile)[0] + "_cofold_out.csv"

    
    # Run RNAcofold
    logging.info("Running RNAcofold")
    command = f'RNAcofold -p0  --output-format=D --jobs=0 --noPS --noconv {rnaCofoldInFile}'
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
    # Convert sequence to uppercase to handle mixed cases
    seq = seq.upper()
    
    # Count G and C in the sequence
    g_count = seq.count('G')
    c_count = seq.count('C')
    
    # Calculate GC content as a percentage
    gc_percentage = (g_count + c_count) / len(seq)
    
    return gc_percentage   

def longest_at_run(seq):
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