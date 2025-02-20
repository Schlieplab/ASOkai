import logging
import os
import subprocess
import shlex
from typing import Optional, Tuple, Any, List

def get_chromosomal_positions_per_transcript(
    transcript: str,
    position_in_transcript: int,
    ensembl_obj: Any,
    k: int,
    ensembl_obj_scaffolds: Optional[Any] = None
) -> Optional[str]:
    """
    Retrieve the absolute chromosomal coordinates corresponding to a specific relative position within a transcript.

    This function calculates the chromosomal coordinates for a given position within a transcript.
    It first attempts to locate the transcript using the main Ensembl object, and if not found, uses an optional
    scaffold annotation.

    Parameters:
        transcript (str): The Ensembl transcript ID.
        position_in_transcript (int): The 1-based position within the transcript.
        ensembl_obj (Any): The main EnsemblRelease object for querying transcript data.
        k (int): The window length for coordinate calculation.
        ensembl_obj_scaffolds (Optional[Any]): Optional Genome object for scaffold annotations.

    Returns:
        Optional[str]: A string key in the format 'contig:start_pos-end_pos:strand', or None if the transcript is not found.
    """
    def calculate_chromosomal_positions(
        exon_intervals: List[Tuple[int, int]], pos: int, strand: str, k: int
    ) -> Tuple[int, int]:
        def return_pos(p: int) -> int:
            accumulated = 0
            if strand == '-':
                for exon in exon_intervals:
                    exon_length = exon[1] - exon[0] + 1
                    if (accumulated + exon_length) > p:
                        return exon[1] - (p - accumulated) + 1
                    accumulated += exon_length
            elif strand == '+':
                for exon in reversed(exon_intervals):
                    exon_length = exon[1] - exon[0] + 1
                    if (accumulated + exon_length) > p:
                        return exon[0] + (p - accumulated) - 1
                    accumulated += exon_length
            return p

        # Sort exons in descending order by start coordinate.
        exon_intervals = sorted(exon_intervals, key=lambda x: x[0], reverse=True)
        if strand == '-':
            return return_pos(pos + k - 1), return_pos(pos)
        elif strand == '+':
            return return_pos(pos), return_pos(pos + k - 1)
        else:
            return pos, pos

    transcript_id = transcript.split(".")[0]
    try:
        transcript_obj = ensembl_obj.transcript_by_id(transcript_id=transcript_id)
    except Exception as e:
        logging.warning(f"Main lookup failed for transcript {transcript_id}: {e}")
        if ensembl_obj_scaffolds:
            try:
                transcript_obj = ensembl_obj_scaffolds.transcript_by_id(transcript_id=transcript_id)
            except Exception as e2:
                logging.warning(f"Scaffold lookup failed for transcript {transcript_id}: {e2}")
                return None
        else:
            return None

    start_pos, end_pos = calculate_chromosomal_positions(
        transcript_obj.exon_intervals,
        position_in_transcript,
        transcript_obj.strand,
        k
    )
    key = f'{transcript_obj.contig}:{start_pos}-{end_pos}:{transcript_obj.strand}'
    return key


def get_seq_by_transcript_position(
    transcript: str,
    position_in_transcript: int,
    ensembl_obj: Any,
    k: int,
    ensembl_obj_scaffolds: Optional[Any] = None
) -> Optional[str]:
    """
    Retrieve a subsequence of length k from a transcript, starting at a specified 1-based position.

    Parameters:
        transcript (str): The Ensembl transcript ID.
        position_in_transcript (int): 1-based starting position within the transcript.
        ensembl_obj (Any): The main EnsemblRelease object.
        k (int): The length of the subsequence.
        ensembl_obj_scaffolds (Optional[Any]): Optional Genome object for scaffold annotations.

    Returns:
        Optional[str]: The subsequence of length k, or None if the transcript is not found or indexes are out-of-bound.
    """
    transcript_id = transcript.split(".")[0]
    try:
        transcript_obj = ensembl_obj.transcript_by_id(transcript_id=transcript_id)
    except Exception as e:
        logging.warning(f"Main lookup failed for transcript {transcript_id}: {e}")
        if ensembl_obj_scaffolds:
            try:
                transcript_obj = ensembl_obj_scaffolds.transcript_by_id(transcript_id=transcript_id)
            except Exception as e2:
                logging.warning(f"Scaffold lookup failed for transcript {transcript_id}: {e2}")
                return None
        else:
            return None

    idx = position_in_transcript - 1  # Convert to 0-based index.
    seq_len = len(transcript_obj.sequence)
    # Guard against indices out of bounds.
    if idx < 0 or (idx + k) > seq_len:
        return None
    return transcript_obj.sequence[idx:idx + k]


def get_rna_cofold_energy(rnaCofoldInFile: str, paramFile: str) -> str:
    """
    Run RNAcofold to calculate RNA secondary structure energies and save the results to a CSV file.

    Parameters:
        rnaCofoldInFile (str): Path to the RNA sequences input file for RNAcofold.
        paramFile (str): Parameter file for RNAcofold.

    Returns:
        str: The path to the output CSV file containing RNAcofold results.
    """
    outFile = os.path.splitext(rnaCofoldInFile)[0] + "_cofold_out.csv"
    logging.info("Running RNAcofold")
    command = f'RNAcofold -p0 --output-format=D --jobs=0 --noPS --noconv {rnaCofoldInFile} {paramFile}'
    logging.info(f"Command: {command}")

    with open(outFile, 'w') as rcfOutFile:
        process = subprocess.Popen(
            shlex.split(command), stdout=rcfOutFile, stderr=subprocess.PIPE, text=True
        )
        while True:
            output = process.stderr.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                logging.info(output.strip())
        process.wait()
    return outFile


def get_exon_id(pos_in_transcript: int, transcript: Any) -> Optional[str]:
    """
    Retrieve the exon ID corresponding to a given position within a transcript.

    Parameters:
        pos_in_transcript (int): The position within the transcript.
        transcript (Any): A transcript object containing exon information and strand orientation.

    Returns:
        Optional[str]: The exon ID where the position is located, or None if not found.
    """
    accumulated = 0
    # Sort exons by start coordinate; process in reverse order for '-' strand.
    exons = sorted(transcript.exons, key=lambda exon: exon.start, reverse=True)
    if transcript.strand == '-':
        for exon in exons:
            exon_length = exon.end - exon.start + 1
            if (accumulated + exon_length) > pos_in_transcript:
                return exon.exon_id
            accumulated += exon_length
    elif transcript.strand == '+':
        for exon in reversed(exons):
            exon_length = exon.end - exon.start + 1
            if (accumulated + exon_length) > pos_in_transcript:
                return exon.exon_id
            accumulated += exon_length
    return None


def get_gc_content(seq: str) -> float:
    """
    Calculate the GC content of a nucleotide sequence.

    Parameters:
        seq (str): The nucleotide sequence.

    Returns:
        float: The proportion of nucleotides that are G or C.
    """
    seq = seq.upper()
    if not seq:
        return 0.0
    g_count = seq.count('G')
    c_count = seq.count('C')
    return (g_count + c_count) / len(seq)


def longest_at_run(seq: str) -> float:
    """
    Calculate the proportion occupied by the longest contiguous run of A or T nucleotides.

    Parameters:
        seq (str): The nucleotide sequence.

    Returns:
        float: The length of the longest A/T run divided by the total length of the sequence.
    """
    seq = seq.upper()
    if not seq:
        return 0.0
    max_at_run = 0
    current_at_run = 0
    for nucleotide in seq:
        if nucleotide in 'AT':
            current_at_run += 1
            max_at_run = max(max_at_run, current_at_run)
        else:
            current_at_run = 0
    return max_at_run / len(seq)


def longest_t_run(seq: str) -> float:
    """
    Calculate the proportion occupied by the longest contiguous run of T nucleotides.

    Parameters:
        seq (str): The nucleotide sequence.

    Returns:
        float: The length of the longest T run divided by the total length of the sequence.
    """
    seq = seq.upper()
    if not seq:
        return 0.0
    max_t_run = 0
    current_t_run = 0
    for nucleotide in seq:
        if nucleotide == 'T':
            current_t_run += 1
            max_t_run = max(max_t_run, current_t_run)
        else:
            current_t_run = 0
    return max_t_run / len(seq)