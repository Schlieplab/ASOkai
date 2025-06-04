import os
import logging
from typing import List, Set, Tuple, Dict, Optional, Callable
from Bio.SeqUtils import gc_fraction
from Bio.Seq import Seq

from src.utils.rna_cofold import RNACofold
from src.utils.genome_utils import Gene, Transcript, Exon, CandidateTarget, RepeatedSite

# Configure basic logging if not already configured globally
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class CandidateTargetsManager:
    """
    Manages the extraction, characterization, filtering, and output of candidate targets
    and their associated repeated sites.
    """

    def __init__(self,
                 target_gene: Gene,
                 k: int,
                 gc_bounds: Tuple[float, float],
                 rna_cofold_temperature: float,
                 rna_cofold_params_file: Optional[str],
                 multiplicity_layout: List[int]):
        """
        Initializes the CandidateManager.

        Args:
            target_gene: The Gene object (or TargetGene instance) for which to find candidates.
            k: The length of k-mers (oligonucleotides) to extract.
            gc_bounds: Tuple specifying the lower and upper bounds for GC content.
            rna_cofold_temperature: Temperature for RNACofold calculations.
            rna_cofold_params_file: Path to parameters file for RNACofold.
            multiplicity_layout: List of integers specifying the layout for core/flank regions,
                                 used for constraint generation and repeated site definition.
                                 Expected format: [left_flank_len, core_len, right_flank_len]
        """
        self.target_gene = target_gene
        self.k = k
        self.gc_bounds = gc_bounds
        self.multiplicity_layout = multiplicity_layout
        
        self.rna_cofold = RNACofold(temperature=rna_cofold_temperature, params_file_path=rna_cofold_params_file)
        
        self.candidates: Dict[str, CandidateTarget] = {}
        self._next_candidate_s_index: int = 1
        
        if not (len(self.multiplicity_layout) == 3 and sum(self.multiplicity_layout) == self.k):
            logging.warning(
                f"Multiplicity layout {self.multiplicity_layout} sum ({sum(self.multiplicity_layout)}) "
                f"does not match k-mer length ({self.k}). This might lead to issues in constraint "
                f"generation or repeated site analysis."
            )
        logging.info(f"CandidateManager initialized for gene {self.target_gene.gene_id} with k={self.k}.")

    def _generate_candidate_id(self) -> str:
        """Generates a unique sequential ID for candidates (e.g., S000001)."""
        s_id = f"S{str(self._next_candidate_s_index).zfill(6)}"
        self._next_candidate_s_index += 1
        return s_id

    def _kmers(self, sequence: str) -> Set[Tuple[str, int]]:
        """
        Generate k-mers from the input sequence and filter them based on GC bounds.
        Args:
            sequence: The input DNA sequence from which k-mers are generated.
        Returns:
            A set of tuples, where each tuple contains a k-mer and its 1-based start position.
        """
        if not sequence or len(sequence) < self.k:
            return set()
            
        kmers_list = []
        for i in range(len(sequence) - self.k + 1):
            kmer = sequence[i:i + self.k]
            # Ensure gc_fraction input is uppercase for BioPython > 1.79 consistency
            if self.gc_bounds[0] <= gc_fraction(kmer.upper())*100 <= self.gc_bounds[1]:
                kmers_list.append((kmer, i + 1))
        return set(kmers_list)

    def _get_constraint_string(self, force_core_alignment: bool) -> Optional[str]:
        """Generates ViennaRNA constraint string based on multiplicity_layout."""
        if force_core_alignment and len(self.multiplicity_layout) == 3:
            target_constraint = ('.' * self.multiplicity_layout[0] + 
                                 '|' * self.multiplicity_layout[1] + 
                                 '.' * self.multiplicity_layout[2])
            oligo_constraint = ('.' * self.multiplicity_layout[2] + 
                                '|' * self.multiplicity_layout[1] + 
                                '.' * self.multiplicity_layout[0])
            return f"{target_constraint}&{oligo_constraint}"
        elif force_core_alignment:
            logging.warning("Cannot force core alignment: multiplicity_layout is not of length 3.")
        return None

    def extract_candidate_targets(self, force_core_alignment_dG: bool = False):
        """
        Extracts candidate targets from the target gene's transcripts.
        Populates self.candidates.
        Args:
            force_core_alignment_dG: If True, use constraints for dG_binding calculation.
        """
        self.candidates.clear()
        self._next_candidate_s_index = 1
        logging.info(f"Starting candidate extraction for gene {self.target_gene.gene_id}, k={self.k}.")

        constraint_string = self._get_constraint_string(force_core_alignment_dG)
        
        # Key: (kmer_sequence, chromosomal_position_str)
        # Value: Temp CandidateTarget object (to collect transcripts/exons)
        unique_raw_sites: Dict[Tuple[str, str], CandidateTarget] = {}

        if not self.target_gene.transcripts:
            logging.warning(f"Gene {self.target_gene.gene_id} has no transcripts. No candidates will be extracted.")
            return

        for transcript in self.target_gene.transcripts:
            if not transcript.sequence:
                logging.debug(f"Transcript {transcript.transcript_id} has no sequence. Skipping.")
                continue

            kmers_set = self._kmers(transcript.sequence)

            for kmer_seq, pos_in_transcript in kmers_set:
                chrom_pos_str = transcript.get_chromosomal_window(pos_in_transcript, self.k)
                if chrom_pos_str is None:
                    logging.debug(f"Could not map k-mer {kmer_seq} in transcript {transcript.transcript_id} to genomic coordinates.")
                    continue
                
                exon = transcript.get_exon_by_position(pos_in_transcript)
                site_key = (kmer_seq, chrom_pos_str)

                if site_key not in unique_raw_sites:
                    homodimer_dG = self.rna_cofold.calculate_homodimer_binding_dg(kmer_seq)
                    oligo_seq_rc = str(Seq(kmer_seq).reverse_complement())
                    binding_dg = self.rna_cofold.calculate_binding_dg(kmer_seq, oligo_seq_rc, constraint_string)
                    
                    raw_candidate = CandidateTarget(
                        sequence=kmer_seq,
                        chromosomal_position=chrom_pos_str,
                        gene_id=self.target_gene.gene_id,
                        transcripts=[transcript],
                        exons=[exon] if exon else [],
                        dG_binding=binding_dg,
                        oligo_homodimer_dG=homodimer_dG
                    )
                    unique_raw_sites[site_key] = raw_candidate
                else:
                    unique_raw_sites[site_key].transcripts.append(transcript)
                    if exon and exon not in unique_raw_sites[site_key].exons: # Avoid duplicate exons
                        unique_raw_sites[site_key].exons.append(exon)
        
        for raw_site_obj in unique_raw_sites.values():
            candidate_id = self._generate_candidate_id()
            raw_site_obj.id = candidate_id
            self.candidates[candidate_id] = raw_site_obj
            
        logging.info(f"Extracted {len(self.candidates)} unique candidate targets for gene {self.target_gene.gene_id}.")

    def find_repeated_sites(self, 
                            pre_mrna_sequence: str, 
                            force_core_alignment_dG: bool = False, 
                            max_ddg_threshold: Optional[float] = None):
        """
        Finds repeated sites for each candidate within the provided pre_mrna_sequence.
        Args:
            pre_mrna_sequence: The pre-mRNA sequence of the target gene to search within.
            force_core_alignment_dG: If True, use constraints for dG calculations of repeated sites.
            max_ddg_threshold: If set, only repeated sites with ddG <= threshold are kept.
        """
        if not pre_mrna_sequence:
            logging.warning("Pre-mRNA sequence not provided. Cannot find repeated sites.")
            return
        if not self.candidates:
            logging.warning("No candidates extracted yet. Call extract_candidates() first.")
            return
        if not (self.target_gene.chromosome and self.target_gene.start is not None and \
                self.target_gene.end is not None and self.target_gene.strand):
            logging.error("Target gene is missing essential coordinate information (chromosome, start, end, strand). Cannot map repeated sites.")
            return


        logging.info(f"Finding repeated sites for {len(self.candidates)} candidates.")
        constraint_string = self._get_constraint_string(force_core_alignment_dG)
        
        core_offset = self.multiplicity_layout[0]
        core_len = self.multiplicity_layout[1]
        expected_full_site_len = sum(self.multiplicity_layout)

        for cand_id, candidate in self.candidates.items():
            candidate.repeated_sites.clear() # Clear previous findings
            
            if len(candidate.sequence) != expected_full_site_len:
                logging.warning(f"Candidate {cand_id} sequence length {len(candidate.sequence)} "
                                f"does not match expected site length {expected_full_site_len} from multiplicity. Skipping repeated sites for it.")
                continue

            core_region_candidate = candidate.sequence[core_offset : core_offset + core_len]
            oligo_rc_candidate = str(Seq(candidate.sequence).reverse_complement())
            
            start_search_pos = 0
            while True:
                pos_core_in_premrna = pre_mrna_sequence.find(core_region_candidate, start_search_pos)
                if pos_core_in_premrna == -1:
                    break
                
                start_search_pos = pos_core_in_premrna + 1 # Next search starts after this match's core

                # Calculate start of the full potential repeated site in pre-mRNA coordinates (0-based)
                potential_site_start_in_premrna = pos_core_in_premrna - core_offset
                
                if potential_site_start_in_premrna < 0 or \
                   (potential_site_start_in_premrna + expected_full_site_len) > len(pre_mrna_sequence):
                    continue # Site out of bounds

                repeated_site_seq = pre_mrna_sequence[potential_site_start_in_premrna : 
                                                      potential_site_start_in_premrna + expected_full_site_len]

                # Map to genomic coordinates
                g_start, g_end = -1, -1
                if self.target_gene.strand == '+':
                    g_start = self.target_gene.start + potential_site_start_in_premrna
                    g_end = g_start + expected_full_site_len - 1
                else: # strand == '-'
                    g_end = self.target_gene.end - potential_site_start_in_premrna
                    g_start = g_end - expected_full_site_len + 1
                
                repeated_site_chrom_pos = f"{self.target_gene.chromosome}:{g_start}-{g_end}:{self.target_gene.strand}"

                if repeated_site_chrom_pos == candidate.chromosomal_position:
                    continue # This is the original candidate site

                binding_dg_repeated = self.rna_cofold.calculate_binding_dg(repeated_site_seq, oligo_rc_candidate, constraint_string)
                
                if candidate.dG_binding is None: # Should not happen if extract_candidates was run
                    logging.warning(f"Candidate {cand_id} dG_binding is None. Cannot calculate ddG.")
                    continue
                
                ddg = binding_dg_repeated - candidate.dG_binding

                if max_ddg_threshold is None or ddg <= max_ddg_threshold:
                    rep_site = RepeatedSite(
                        sequence=repeated_site_seq,
                        chromosomal_position=repeated_site_chrom_pos,
                        parent_target_id=cand_id,
                        ddg_to_parent=ddg
                    )
                    candidate.add_repeated_site(rep_site)
        logging.info("Finished finding repeated sites.")

    def filter_all_candidate_repeated_sites(self, ddg_threshold: float):
        """Filters repeated sites for all candidates based on a ddG threshold."""
        logging.info(f"Filtering repeated sites for all candidates with ddG threshold <= {ddg_threshold}.")
        for candidate in self.candidates.values():
            candidate.filter_repeated_sites_by_ddg(ddg_threshold)

    def filter_candidates(self, filter_function: Callable[[CandidateTarget], bool]):
        """
        Filters self.candidates in-place based on a custom filter function.
        The filter_function should take a CandidateTarget object and return True to keep it.
        """
        initial_count = len(self.candidates)
        self.candidates = {
            cid: c for cid, c in self.candidates.items() if filter_function(c)
        }
        logging.info(f"Filtered candidates. Kept {len(self.candidates)} out of {initial_count}.")

    def filter_candidates_by_id_list(self, 
                                     ids_to_keep: Optional[List[str]] = None, 
                                     ids_to_remove: Optional[List[str]] = None):
        """Filters candidates based on lists of IDs to keep or remove."""
        ids_to_keep_set = set(ids_to_keep) if ids_to_keep else set()
        ids_to_remove_set = set(ids_to_remove) if ids_to_remove else set()

        if not ids_to_keep_set and not ids_to_remove_set:
            logging.info("No ID lists provided for filtering, no changes made to candidates.")
            return

        def id_filter_func(candidate: CandidateTarget) -> bool:
            # Start by assuming we keep the candidate
            keep = True
            # If ids_to_keep is specified, candidate must be in this set to be kept.
            if ids_to_keep_set:
                keep = candidate.id in ids_to_keep_set
            
            # If candidate is currently marked to be kept AND ids_to_remove is specified,
            # it must NOT be in ids_to_remove_set.
            if keep and ids_to_remove_set:
                keep = candidate.id not in ids_to_remove_set
            return keep
        
        self.filter_candidates(id_filter_func)

    def filter_candidates_by_sequence_list(self, 
                                           sequences_to_keep: Optional[List[str]] = None, 
                                           sequences_to_remove: Optional[List[str]] = None):
        """Filters candidates based on lists of their sequences to keep or remove."""
        sequences_to_keep_set = set(sequences_to_keep) if sequences_to_keep else set()
        sequences_to_remove_set = set(sequences_to_remove) if sequences_to_remove else set()

        if not sequences_to_keep_set and not sequences_to_remove_set:
            logging.info("No sequence lists provided for filtering, no changes made to candidates.")
            return

        def sequence_filter_func(candidate: CandidateTarget) -> bool:
            if candidate.sequence is None: # Should not happen for valid candidates
                return False
                
            # Start by assuming we keep the candidate
            keep = True
            # If sequences_to_keep is specified, candidate's sequence must be in this set to be kept.
            if sequences_to_keep_set:
                keep = candidate.sequence in sequences_to_keep_set
            
            # If candidate is currently marked to be kept AND sequences_to_remove is specified,
            # its sequence must NOT be in sequences_to_remove_set.
            if keep and sequences_to_remove_set:
                keep = candidate.sequence not in sequences_to_remove_set
            return keep

        self.filter_candidates(sequence_filter_func)

    def get_candidate(self, candidate_id: str) -> Optional[CandidateTarget]:
        return self.candidates.get(candidate_id)

    def get_all_candidates(self) -> List[CandidateTarget]:
        return list(self.candidates.values())

    def generate_gtf(self, 
                     output_path: str, 
                     source_name: str = "ASO_Pipeline", 
                     include_repeated_sites: bool = True):
        """
        Generates a GTF file for the current candidates and optionally their repeated sites.
        Args:
            output_path: Path to save the GTF file.
            source_name: Source field for the GTF records.
            include_repeated_sites: If True, include repeated sites in the GTF.
        """
        logging.info(f"Generating GTF file at {output_path} with source '{source_name}'.")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        written_records = 0
        with open(output_path, 'w') as f_out:
            f_out.write("##gff-version 3\n") # Standard GTF/GFF3 header

            for candidate in self.candidates.values():
                gtf_line_cand = candidate.to_gtf_record(source=source_name, feature_type="candidate_target")
                if gtf_line_cand:
                    f_out.write(gtf_line_cand + "\n")
                    written_records +=1
                
                if include_repeated_sites:
                    for rep_site in candidate.repeated_sites:
                        gtf_line_rep = rep_site.to_gtf_record(source=source_name, feature_type="repeated_site")
                        if gtf_line_rep:
                            f_out.write(gtf_line_rep + "\n")
                            written_records +=1
        
        logging.info(f"Wrote {written_records} records to GTF file: {output_path}")

    def generate_candidate_fasta(self, output_path: str):
        """Generates a FASTA file for the current candidate target sequences."""
        logging.info(f"Generating FASTA file for candidates at {output_path}")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        written_records = 0
        with open(output_path, 'w') as f_out:
            for candidate_id, candidate in self.candidates.items():
                header = f">{candidate_id} gene_id={candidate.gene_id} chrom_pos={candidate.chromosomal_position}"
                f_out.write(header + "\n")
                f_out.write(candidate.sequence + "\n")
                written_records += 1
        logging.info(f"Wrote {written_records} candidate sequences to FASTA: {output_path}")

    def update_pedersen_steady_state(self, pedersen_results: Dict[str, float]):
        """
        Updates the pedersen_steady_state attribute for candidates.
        Args:
            pedersen_results: A dictionary mapping candidate ID (e.g., 'S000001') to
                              the pedersen steady state percentage.
        """
        updated_count = 0
        for cand_id, p_value in pedersen_results.items():
            if cand_id in self.candidates:
                self.candidates[cand_id].pedersen_steady_state = p_value
                updated_count +=1
            else:
                logging.warning(f"Candidate ID {cand_id} from Pedersen results not found in current candidates.")
        logging.info(f"Updated Pedersen steady state for {updated_count} candidates.") 