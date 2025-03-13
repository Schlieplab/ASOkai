import logging
from typing import Optional, Any, List, Dict


def build_transcript_to_genomic_map(
    transcript_obj: Any
) -> Dict[int, int]:
    """
    Build a mapping from transcript positions to genomic positions.
    
    Parameters:
        transcript_obj: A transcript object containing exon_intervals and strand information.
        
    Returns:
        Dict[int, int]: A dictionary mapping transcript positions (1-based) to genomic positions.
    """
    transcript_to_genomic = {}
    
    # Sort exons by genomic position
    sorted_exons = sorted(transcript_obj.exon_intervals, key=lambda x: x[0])
    
    transcript_pos = 1
    
    if transcript_obj.strand == '+':
        # Forward strand: exons are processed in order
        for start, end in sorted_exons:
            exon_length = end - start + 1
            for i in range(exon_length):
                transcript_to_genomic[transcript_pos] = start + i
                transcript_pos += 1
    else:  # strand == '-'
        # Reverse strand: exons are processed in reverse order
        for start, end in reversed(sorted_exons):
            exon_length = end - start + 1
            for i in range(exon_length):
                transcript_to_genomic[transcript_pos] = end - i
                transcript_pos += 1
                
    return transcript_to_genomic


def get_transcript_object(
    transcript: str,
    genome: Any,
    genome_scaffolds: Optional[Any] = None
) -> Optional[Any]:
    """
    Get transcript object from genome or scaffold genome.
    
    Parameters:
        transcript (str): The Ensembl transcript ID.
        genome (Any): The main Genome object for querying transcript data.
        genome_scaffolds (Optional[Any]): Optional Genome object for scaffold annotations.
        
    Returns:
        Optional[Any]: Transcript object if found, None otherwise.
    """
    # Strip version number from transcript ID if present
    transcript_id = transcript.split(".")[0]
    
    # Try to get transcript from main genome
    try:
        transcript_obj = genome.transcript_by_id(transcript_id=transcript_id)
        return transcript_obj
    except Exception as e:
        logging.warning(f"Main lookup failed for transcript {transcript_id}: {e}")
        
        # If main lookup fails, try scaffold genome if provided
        if genome_scaffolds:
            try:
                transcript_obj = genome_scaffolds.transcript_by_id(transcript_id=transcript_id)
                return transcript_obj
            except Exception as e2:
                logging.warning(f"Scaffold lookup failed for transcript {transcript_id}: {e2}")
    
    return None


def get_chromosomal_positions_with_mapping(
    transcript_obj: Any,
    transcript_to_genomic: Dict[int, int],
    positions_in_transcript: List[int],
    k: int,
    verbose: bool = False,
) -> List[Optional[str]]:
    """
    Retrieve the absolute chromosomal coordinates using a pre-built transcript-to-genomic mapping.

    Parameters:
        transcript_obj: The transcript object containing contig and strand information.
        transcript_to_genomic: Dictionary mapping transcript positions to genomic positions.
        positions_in_transcript (List[int]): List of 1-based positions within the transcript.
        k (int): The window length for coordinate calculation.

    Returns:
        List[Optional[str]]: List of string keys in the format 'contig:start_pos-end_pos:strand', 
                            or None for positions that couldn't be mapped.
    """
    results = []
    for pos in positions_in_transcript:
        try:
            start_genomic = transcript_to_genomic.get(pos)
            end_genomic = transcript_to_genomic.get(pos + k - 1)
            
            if start_genomic is None or end_genomic is None:
                if verbose:
                    logging.warning(f"Position {pos} or {pos + k - 1} is outside transcript bounds")
                results.append(None)
                continue
                
            # Ensure start <= end in the output
            start, end = min(start_genomic, end_genomic), max(start_genomic, end_genomic)
            key = f'{transcript_obj.contig}:{start}-{end}:{transcript_obj.strand}'
            results.append(key)
        except Exception as e:
            logging.warning(f"Error calculating position {pos}: {e}")
            results.append(None)
    
    return results


def get_chromosomal_positions_for_transcript(
    transcript: str,
    positions_in_transcript: List[int],
    genome: Any,
    k: int,
    genome_scaffolds: Optional[Any] = None
) -> List[Optional[str]]:
    """
    Retrieve the absolute chromosomal coordinates corresponding to specific positions within a transcript.

    This function calculates the chromosomal coordinates for given positions within a transcript,
    all using the same window length k. It first attempts to locate the transcript using the main 
    Ensembl object, and if not found, uses an optional scaffold annotation.

    Parameters:
        transcript (str): The Ensembl transcript ID.
        positions_in_transcript (List[int]): List of 1-based positions within the transcript.
        genome (Any): The main Genome object for querying transcript data.
        k (int): The window length for coordinate calculation (same for all positions).
        genome_scaffolds (Optional[Any]): Optional Genome object for scaffold annotations.

    Returns:
        List[Optional[str]]: List of string keys in the format 'contig:start_pos-end_pos:strand', 
                            or None for positions that couldn't be mapped.
    """
    # Get transcript object
    transcript_obj = get_transcript_object(transcript, genome, genome_scaffolds)
    
    if not transcript_obj:
        return [None] * len(positions_in_transcript)
    
    # Build transcript position to genomic position mapping
    try:
        transcript_to_genomic = build_transcript_to_genomic_map(transcript_obj)
    except Exception as e:
        logging.error(f"Error building transcript mapping for {transcript}: {e}")
        return [None] * len(positions_in_transcript)
    
    # Use the mapping to get chromosomal positions
    return get_chromosomal_positions_with_mapping(
        transcript_obj, 
        transcript_to_genomic, 
        positions_in_transcript, 
        k
    )


def get_chromosomal_positions_per_transcript(
    transcript: str,
    position_in_transcript: int,
    genome: Any,
    k: int,
    genome_scaffolds: Optional[Any] = None
) -> Optional[str]:
    """
    Backward-compatible wrapper for the new multi-position function.
    
    Retrieves the absolute chromosomal coordinates for a single position within a transcript.
    
    Parameters:
        transcript (str): The Ensembl transcript ID.
        position_in_transcript (int): The 1-based position within the transcript.
        genome (Any): The main Genome object for querying transcript data.
        k (int): The window length for coordinate calculation.
        genome_scaffolds (Optional[Any]): Optional Genome object for scaffold annotations.

    Returns:
        Optional[str]: A string key in the format 'contig:start_pos-end_pos:strand', or None if the transcript is not found.
    """
    results = get_chromosomal_positions_for_transcript(
        transcript=transcript,
        positions_in_transcript=[position_in_transcript],
        genome=genome,
        k=k,
        genome_scaffolds=genome_scaffolds
    )
    return results[0]




def get_seq_by_transcript_position(
    transcript: str,
    position_in_transcript: int,
    genome: Any,
    k: int,
    genome_scaffolds: Optional[Any] = None
) -> Optional[str]:
    """
    Retrieve a subsequence of length k from a transcript, starting at a specified 1-based position.

    Parameters:
        transcript (str): The Ensembl transcript ID.
        position_in_transcript (int): 1-based starting position within the transcript.
        genome (Any): The main EnsemblRelease object.
        k (int): The length of the subsequence.
        genome_scaffolds (Optional[Any]): Optional Genome object for scaffold annotations.

    Returns:
        Optional[str]: The subsequence of length k, or None if the transcript is not found or indexes are out-of-bound.
    """
    transcript_id = transcript.split(".")[0]
    try:
        transcript_obj = genome.transcript_by_id(transcript_id=transcript_id)
    except Exception as e:
        logging.warning(f"Main lookup failed for transcript {transcript_id}: {e}")
        if genome_scaffolds:
            try:
                transcript_obj = genome_scaffolds.transcript_by_id(transcript_id=transcript_id)
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