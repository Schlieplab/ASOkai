from Bio import SeqIO
from Bio.Seq import Seq
import os
import gzip
import re
from typing import Dict, List, Optional, Tuple, Set, Union, Any, Iterator
import logging
from dataclasses import dataclass

class Exon:
    """Class representing an exon within a transcript."""
    def __init__(self, exon_id: str, start: int, end: int, transcript_id: str) -> None:
        self.exon_id: str = exon_id
        self.start: int = start  # 1-based genomic coordinates
        self.end: int = end      # 1-based genomic coordinates
        self.transcript_id: str = transcript_id

class Transcript:
    """Class representing a transcript with exons."""
    def __init__(self, transcript_id: str, gene_id: str, chromosome: str, 
                 start: int, end: int, strand: str, biotype: Optional[str] = None,
                 support_level: Optional[int] = None) -> None:
        self.transcript_id: str = transcript_id
        self.gene_id: str = gene_id
        self.chromosome: str = chromosome
        self.start: int = start  # 1-based genomic coordinates
        self.end: int = end      # 1-based genomic coordinates
        self.strand: str = strand
        self.biotype: Optional[str] = biotype
        self.support_level: Optional[int] = support_level  # 1-5 or None
        self.exons: List[Exon] = []
        self._sequence: Optional[str] = None
        self._genomic_coordinate_map: Optional[Dict[int, int]] = None
    
    def add_exon(self, exon: Exon) -> None:
        """Add an exon to this transcript."""
        self.exons.append(exon)
        # Keep exons sorted by position
        self.exons.sort(key=lambda e: e.start)
        # Reset the coordinate map since exon structure changed
        self._genomic_coordinate_map = None
    
    @property
    def sequence(self) -> Optional[str]:
        """Get the transcript sequence."""
        return self._sequence
    
    @sequence.setter
    def sequence(self, seq: str) -> None:
        """Set the transcript sequence."""
        self._sequence = seq
        
    @property
    def exon_intervals(self) -> List[Tuple[int, int]]:
        """Get the exon intervals for this transcript."""
        return [(exon.start, exon.end) for exon in self.exons]
    
    @property
    def genomic_coordinate_map(self) -> Dict[int, int]:
        """
        Get the cached genomic coordinate map, building it if necessary.
        
        Returns:
            Dict[int, int]: Dictionary mapping transcript positions to genomic positions
        """
        if self._genomic_coordinate_map is None:
            self._genomic_coordinate_map = self._build_genomic_coordinate_map()
        return self._genomic_coordinate_map
    
    def _build_genomic_coordinate_map(self) -> Dict[int, int]:
        """
        Internal method to build a mapping from transcript positions to genomic positions.
        
        Returns:
            Dict[int, int]: Dictionary mapping transcript positions to genomic positions
        """
        if not self.exons:
            return {}
            
        mapping: Dict[int, int] = {}
        transcript_pos: int = 1  # 1-based position in transcript
        
        if self.strand == '+':
            # Forward strand: process exons in genomic order (5' to 3')
            sorted_exons = sorted(self.exons, key=lambda e: e.start)
            
            for exon in sorted_exons:
                exon_length = exon.end - exon.start + 1
                for offset in range(exon_length):
                    mapping[transcript_pos] = exon.start + offset
                    transcript_pos += 1
        else:
            # Reverse strand: process exons in reverse genomic order (5' to 3' for transcript)
            sorted_exons = sorted(self.exons, key=lambda e: e.start, reverse=True)
            
            for exon in sorted_exons:
                exon_length = exon.end - exon.start + 1
                for offset in range(exon_length):
                    mapping[transcript_pos] = exon.end - offset
                    transcript_pos += 1
                    
        return mapping
    
    def get_exon_by_position(self, position: int) -> Optional[Exon]:
        """
        Get the exon containing a specific position in the transcript.
        
        Args:
            position (int): 1-based position in the transcript
            
        Returns:
            Optional[Exon]: The exon containing the position, or None if not found
        """
        if position < 1 or not self.exons:
            return None
            
        current_pos: int = 1
        
        # Sort exons based on strand direction
        if self.strand == '+':
            exon_order = sorted(self.exons, key=lambda e: e.start)
        else:  # reverse strand
            exon_order = sorted(self.exons, key=lambda e: e.start, reverse=True)
            
        for exon in exon_order:
            exon_length = exon.end - exon.start + 1
            if current_pos <= position < current_pos + exon_length:
                return exon
            current_pos += exon_length
            
        return None
        
    def get_subsequence(self, start_pos: int, length: int) -> Optional[str]:
        """
        Get a subsequence from this transcript starting at the specified position.
        
        Args:
            start_pos (int): 1-based start position in the transcript
            length (int): Length of the subsequence to return
            
        Returns:
            Optional[str]: The subsequence of specified length, or None if invalid position/length
        """
        if not self._sequence:
            return None
            
        # Convert to 0-based indexing for Python string operations
        idx = start_pos - 1
        
        # Check bounds
        if idx < 0 or idx + length > len(self._sequence):
            return None
            
        return self._sequence[idx:idx + length]
        
    def get_chromosomal_positions(self, positions: List[int], window_length: int) -> List[Optional[str]]:
        """
        Get chromosomal coordinates for specified positions within this transcript.
        
        Args:
            positions (List[int]): List of 1-based positions within the transcript
            window_length (int): Length of the window/sequence at each position
            
        Returns:
            List[Optional[str]]: Chromosomal coordinates in format "chrom:start-end:strand"
        """
        # Build mapping from transcript to genomic coordinates
        mapping = self.genomic_coordinate_map
        if not mapping:
            return [None] * len(positions)
            
        results: List[Optional[str]] = []
        
        for pos in positions:
            try:
                # Check if both start and end positions are mapped
                start_genomic = mapping.get(pos)
                end_genomic = mapping.get(pos + window_length - 1)
                
                if start_genomic is None or end_genomic is None:
                    results.append(None)
                    continue
                    
                # Sort the coordinates in ascending order regardless of strand
                start, end = min(start_genomic, end_genomic), max(start_genomic, end_genomic)
                
                # Format result string
                result = f"{self.chromosome}:{start}-{end}:{self.strand}"
                results.append(result)
                
            except Exception as e:
                results.append(None)
                
        return results
    
    def get_chromosomal_position(
        self, position: int, window_length: int
        ) -> Optional[str]:
            """
            Get chromosomal position for a single position within a transcript.
            
            Args:
                transcript_id (str): The ID of the transcript
                position (int): 1-based position within the transcript
                window_length (int): Length of the window starting at the position
                
            Returns:
                Optional[str]: Chromosomal coordinates in format "chrom:start-end:strand"
            """
            results = self.get_chromosomal_positions(
                positions=[position],
                window_length=window_length
            )
            return results[0] if results else None

class Gene:
    """Class representing a gene with transcripts."""
    def __init__(self, gene_id: str, gene_name: str, chromosome: str, 
                 start: int, end: int, strand: str, biotype: Optional[str] = None) -> None:
        self.gene_id: str = gene_id
        self.gene_name: str = gene_name
        self.chromosome: str = chromosome
        self.start: int = start  # 1-based genomic coordinates
        self.end: int = end      # 1-based genomic coordinates
        self.strand: str = strand
        self.biotype: Optional[str] = biotype
        self.transcripts: List[Transcript] = []
    
    def add_transcript(self, transcript: Transcript) -> None:
        """Add a transcript to this gene."""
        self.transcripts.append(transcript)
    
    def get_transcripts_by_support_level(self, max_level: Optional[int] = None) -> List[Transcript]:
        """
        Get transcripts filtered by support level.
        
        Args:
            max_level (Optional[int]): Maximum support level to include (1-5), 
                                      or None to include all transcripts
            
        Returns:
            List[Transcript]: List of transcripts with support level less than or equal to max_level,
                             or all transcripts if max_level is None
        """
        if max_level is None:
            return self.transcripts
        
        return [t for t in self.transcripts 
                if t.support_level is not None and t.support_level <= max_level]

class Genome:
    def __init__(self, reference_name: str, annotation_version: Optional[str] = None,
                 gtf_path: Optional[str] = None, 
                 transcript_fasta_paths: Optional[Union[str, List[str]]] = None) -> None:
        """
        A Genome class using Biopython to load and manipulate genome sequences.

        Parameters:
        - reference_name: E.g. 'GRCm38'
        - annotation_version: Annotation version/release (e.g. 113)
        - gtf_path: Path to the GTF file
        - transcript_fasta_paths: Path(s) to transcript FASTA file(s)
        """
        
        self.reference_name: str = reference_name
        self.annotation_version: Optional[str] = annotation_version
        self.gtf_path: Optional[str] = gtf_path
        
        # Handle either a single path or a list of paths
        if transcript_fasta_paths is not None:
            if isinstance(transcript_fasta_paths, list):
                self.transcript_fasta_paths: List[str] = transcript_fasta_paths
            else:
                self.transcript_fasta_paths: List[str] = [transcript_fasta_paths]
        else:
            self.transcript_fasta_paths: List[str] = []
        
        
        # Initialize data structures
        self._genes: Dict[str, Gene] = {}  # gene_id -> Gene
        self._transcripts: Dict[str, Transcript] = {}  # transcript_id -> Transcript
        self._transcript_sequences: Dict[str, str] = {}  # transcript_id -> sequence
        self._exons: Dict[str, Exon] = {}  # exon_id -> Exon
        self._indexed: bool = False
        
    
    def index(self, overwrite: bool = False) -> None:
        """
        Parse annotation files and build indices for genes, transcripts, exons, and sequences.
        
        Args:
            overwrite: If True, rebuild indices even if they already exist
        """
        if self._indexed and not overwrite:
            return
        
        # Parse GTF file to build gene/transcript/exon data structures
        self._parse_gtf()
        
        # Parse transcript FASTA files to get sequences
        self._parse_transcript_fasta()
        
        self._indexed = True
        
    def _parse_gtf(self) -> None:
        """Parse GTF file to extract gene, transcript, and exon information."""
        if not self.gtf_path or not os.path.exists(self.gtf_path):
            raise FileNotFoundError(f"GTF file not found: {self.gtf_path}")
        
        # Determine if file is gzipped
        is_gzipped: bool = self.gtf_path.endswith('.gz')
        open_func: Any = gzip.open if is_gzipped else open
        
        # Track current gene and transcript when parsing
        current_gene: Optional[Gene] = None
        current_transcript: Optional[Transcript] = None
        
        with open_func(self.gtf_path, 'rt') as gtf:
            for line in gtf:
                # Skip comments/headers
                if line.startswith('#'):
                    continue
                
                fields: List[str] = line.strip().split('\t')
                if len(fields) < 9:  # GTF has at least 9 fields
                    continue
                
                # Extract feature fields
                seqname, source, feature_type, start, end, score, strand, frame, attributes = fields
                
                # Skip if not gene, transcript, or exon
                if feature_type not in ['gene', 'transcript', 'exon']:
                    continue
                
                # Parse attributes
                attr_dict: Dict[str, str] = {}
                for attr in attributes.split(';'):
                    attr = attr.strip()
                    if not attr:
                        continue
                    try:
                        key, value = attr.split(' ', 1)
                        attr_dict[key] = value.strip('"')
                    except ValueError:
                        pass
                
                # Process different feature types
                if feature_type == 'gene':
                    gene_id: Optional[str] = attr_dict.get('gene_id')
                    gene_name: str = attr_dict.get('gene_name', gene_id)
                    biotype: Optional[str] = attr_dict.get('gene_biotype', attr_dict.get('biotype', None))
                    
                    if gene_id:
                        gene = Gene(
                            gene_id=gene_id,
                            gene_name=gene_name,
                            chromosome=seqname,
                            start=int(start),
                            end=int(end),
                            strand=strand,
                            biotype=biotype
                        )
                        self._genes[gene_id] = gene
                        current_gene = gene
                
                elif feature_type == 'transcript' and current_gene:
                    transcript_id: Optional[str] = attr_dict.get('transcript_id')
                    gene_id: Optional[str] = attr_dict.get('gene_id')
                    biotype: Optional[str] = attr_dict.get('transcript_biotype', attr_dict.get('biotype', None))
                    
                    # Extract support level - could be 'transcript_support_level' or 'tsl'
                    support_level_str: Optional[str] = attr_dict.get('transcript_support_level', 
                                                                    attr_dict.get('tsl', None))
                    support_level: Optional[int] = None
                    
                    # Parse support level if it exists
                    if support_level_str:
                        # Sometimes formatted as "1 (assigned)", so extract just the number
                        match = re.match(r'^(\d+)', support_level_str)
                        if match:
                            try:
                                support_level = int(match.group(1))
                            except ValueError:
                                pass  # Keep as None if conversion fails
                    
                    if transcript_id and gene_id:
                        transcript = Transcript(
                            transcript_id=transcript_id,
                            gene_id=gene_id,
                            chromosome=seqname,
                            start=int(start),
                            end=int(end),
                            strand=strand,
                            biotype=biotype,
                            support_level=support_level
                        )
                        self._transcripts[transcript_id] = transcript
                        
                        # Add to gene if it exists
                        if gene_id in self._genes:
                            self._genes[gene_id].add_transcript(transcript)
                        
                        current_transcript = transcript
                
                elif feature_type == 'exon' and current_transcript:
                    exon_id: str = attr_dict.get('exon_id', f"{seqname}:{start}-{end}")
                    transcript_id: Optional[str] = attr_dict.get('transcript_id')
                    
                    if exon_id and transcript_id and transcript_id in self._transcripts:
                        exon = Exon(
                            exon_id=exon_id,
                            start=int(start),
                            end=int(end),
                            transcript_id=transcript_id
                        )
                        self._exons[exon_id] = exon
                        self._transcripts[transcript_id].add_exon(exon)
    
    def _parse_transcript_fasta(self) -> None:
        """Parse transcript FASTA files to extract sequences."""
        for fasta_path in self.transcript_fasta_paths:
            if not os.path.exists(fasta_path):
                print(f"Warning: FASTA file not found: {fasta_path}")
                continue
            
            # Determine if file is gzipped
            is_gzipped: bool = fasta_path.endswith('.gz')
            open_func: Any = gzip.open if is_gzipped else open
            
            # Parse FASTA file
            with open_func(fasta_path, 'rt') as fasta_file:
                for record in SeqIO.parse(fasta_file, 'fasta'):
                    # Extract transcript ID from header (may need adjustment based on format)
                    header_parts: List[str] = record.id.split('|')
                    if len(header_parts) > 1:
                        # Try to extract a clean transcript ID
                        transcript_id: str = header_parts[0].split('.')[0]
                    else:
                        transcript_id: str = record.id.split('.')[0]
                    
                    # Store sequence if we have this transcript
                    if transcript_id in self._transcripts:
                        sequence: str = str(record.seq)
                        self._transcript_sequences[transcript_id] = sequence
                        self._transcripts[transcript_id].sequence = sequence
    
    def gene_by_id(self, gene_id: str) -> Gene:
        """Get a gene by its ID."""
        if not self._indexed:
            self.index()
        
        if gene_id in self._genes:
            return self._genes[gene_id]
        
        raise ValueError(f"Gene not found with ID: {gene_id}")
    
    def transcript_by_id(self, transcript_id: str) -> Transcript:
        """Get a transcript by its ID."""
        if not self._indexed:
            self.index()
        
        if transcript_id in self._transcripts:
            return self._transcripts[transcript_id]
        
        raise ValueError(f"Transcript not found with ID: {transcript_id}")
    
    def transcripts(self) -> List[Transcript]:
        """Get all transcripts."""
        if not self._indexed:
            self.index()
        
        return list(self._transcripts.values())
    
    def genes(self) -> List[Gene]:
        """Get all genes."""
        if not self._indexed:
            self.index()
        
        return list(self._genes.values())
    
    def get_sequence_for_transcript_id(self, transcript_id: str) -> str:
        """Get the sequence for a transcript by ID."""
        if not self._indexed:
            self.index()
        
        if transcript_id in self._transcript_sequences:
            return self._transcript_sequences[transcript_id]
        
        raise ValueError(f"No sequence found for transcript: {transcript_id}")
    
    def get_transcript_subsequence(self, transcript_id: str, position: int, length: int) -> Optional[str]:
        """
        Get a subsequence from a transcript by ID.
        
        Args:
            transcript_id (str): The ID of the transcript
            position (int): 1-based position within the transcript
            length (int): Length of the subsequence to extract
            
        Returns:
            Optional[str]: The requested subsequence, or None if not available
        """
        if not self._indexed:
            self.index()
            
        # Get the base ID without version if present
        base_id = transcript_id.split('.')[0]
        
        try:
            transcript = self.transcript_by_id(base_id)
            return transcript.get_subsequence(position, length)
        except ValueError:
            return None
    
    def get_chromosomal_positions(
        self, transcript_id: str, positions: List[int], window_length: int
    ) -> List[Optional[str]]:
        """
        Get chromosomal positions for multiple positions within a transcript.
        
        Args:
            transcript_id (str): The ID of the transcript
            positions (List[int]): List of 1-based positions within the transcript
            window_length (int): Length of the window at each position
            
        Returns:
            List[Optional[str]]: List of chromosomal coordinates in format "chrom:start-end:strand"
        """
        if not self._indexed:
            self.index()
            
        # Get the base ID without version if present
        base_id = transcript_id.split('.')[0]
        
        try:
            transcript = self.transcript_by_id(base_id)
            return transcript.get_chromosomal_positions(positions, window_length)
        except ValueError:
            # Return None for each position if transcript not found
            return [None] * len(positions)
    
    def get_chromosomal_position(
        self, transcript_id: str, position: int, window_length: int
    ) -> Optional[str]:
        """
        Get chromosomal position for a single position within a transcript.
        
        Args:
            transcript_id (str): The ID of the transcript
            position (int): 1-based position within the transcript
            window_length (int): Length of the window starting at the position
            
        Returns:
            Optional[str]: Chromosomal coordinates in format "chrom:start-end:strand"
        """
        results = self.get_chromosomal_positions(
            transcript_id=transcript_id,
            positions=[position],
            window_length=window_length
        )
        return results[0] if results else None
    
    def get_exon_at_transcript_position(self, transcript_id: str, position: int) -> Optional[Exon]:
        """
        Get the exon containing a specific position in a transcript.
        
        Args:
            transcript_id (str): The ID of the transcript
            position (int): 1-based position within the transcript
            
        Returns:
            Optional[Exon]: The exon containing the position, or None if not found
        """
        if not self._indexed:
            self.index()
            
        # Get the base ID without version if present
        base_id = transcript_id.split('.')[0]
        
        try:
            transcript = self.transcript_by_id(base_id)
            return transcript.get_exon_by_position(position)
        except ValueError:
            return None

@dataclass
class Site:
    sequence: Optional[str] = None
    chromosomal_position: Optional[str] = None
    
    def __len__(self):
        return len(self.sequence) if self.sequence else 0
    


@dataclass
class TargetSite(Site):
    gene_id: Optional[str] = None
    transcripts: Optional[List[Transcript]] = None
    exons: Optional[List[Exon]] = None
    dG: Optional[float] = None

    def __post_init__(self):
        if self.transcripts is None:
            self.transcripts = []
        if self.exons is None:
            self.exons = []


