import logging
import multiprocessing
from tqdm import tqdm
import pandas as pd
import configparser
import os


# Create a configparser object
config = configparser.ConfigParser()

# Read the configuration file
config.read('config.ini')

def get_chromosomal_positions_per_transcript(row, ensembl_obj, ensembl_obj_scaffolds, transcript_map_dict):
    transcript_id = row[2].split(".")[0]
    chromosome, _ = transcript_map_dict[transcript_id].split(':')

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
        row[3],
        transcript.strand
    )
    
    key = f'{chromosome}:{start_pos}-{end_pos}:{transcript.strand}'
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


def calculate_occurances(transcript_map_dict, ensembl_obj, ensembl_obj_scaffolds, candidates):
    """
    Calculate the number of distinct positions a sequence occurs at.
    """
    distinct_positions = set()


                
    
    def rcheck(row):

        key = get_chromosomal_positions_per_transcript(row, ensembl_obj, ensembl_obj_scaffolds, transcript_map_dict)
        
        if key not in distinct_positions:
            distinct_positions.add(key)

    candidates.apply(lambda row: rcheck(row), axis=1)
    
    return len(distinct_positions)

def worker(seq, transcript_map_dict, ensembl_obj, ensembl_obj_scaffolds, candidates):
    """
    Worker function to calculate occurrences for a given sequence.
    """
    return seq, calculate_occurances(transcript_map_dict, ensembl_obj, ensembl_obj_scaffolds, candidates)

def create_occurrence_dict(unique_seqs, transcript_map_dict, ensembl_obj, ensembl_obj_scaffolds, sam_out):
    """
    Create a dictionary of sequence occurrences using multiprocessing.
    """
    num_cpus = os.cpu_count()
    with multiprocessing.Pool(processes=num_cpus) as pool:
        pbar = tqdm(total=len(unique_seqs), desc="Processing Sequences", position=0, leave=True)

        results = []
        async_results = [pool.apply_async(worker, (seq, transcript_map_dict, ensembl_obj, ensembl_obj_scaffolds, sam_out[sam_out[9] == seq]), 
                                          callback=lambda _: pbar.update()) for seq in unique_seqs]

        for r in async_results:
            results.append(r.get())

        pbar.close()

    return dict(results)

def get_kmer_occurances(sam_out, transcript_gene_mapping, ensembl_obj, ensembl_obj_scaffolds):
    """
    Main function to get k-mer occurrences and add them to the SAM output.
    """
    transcript_map_dict = dict(zip(transcript_gene_mapping[0], transcript_gene_mapping[3]))
    unique_seqs = sam_out[9].unique()
    print(f"Unique sequences count: {len(unique_seqs)}")
    occurrence_dict = create_occurrence_dict(unique_seqs, transcript_map_dict, ensembl_obj, ensembl_obj_scaffolds, sam_out)
    sam_out['occurance'] = sam_out.apply(lambda x: f'KM:i:{occurrence_dict[x[9]]}', axis=1)
    return sam_out

