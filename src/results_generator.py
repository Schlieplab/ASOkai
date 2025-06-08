import os
import logging
from typing import Dict, Optional, List

import polars as pl
from Bio.Seq import Seq
from Bio.SeqUtils import gc_fraction # For GC content if needed directly, though CandidateManager handles it mostly

from . import CandidateTargetsManager
from .utils import GenomeUtils
from .sequence_analysis import longest_at_run, longest_t_run

class ResultsGenerator:
    """
    Generates various output files (CSV report, GTF, FASTA) from processed candidates
    managed by a CandidateManager instance.
    """

    def __init__(self, 
                 candidate_manager: CandidateTargetsManager, 
                 target_gene_species: str,
                 base_output_dir: str):
        """
        Initializes the ResultsGenerator.

        Args:
            candidate_manager: An instance of CandidateManager containing the processed candidates.
            target_gene_species: The species of the target gene (e.g., "homo_sapiens", "mus_musculus") 
                                 used for constructing Ensembl links.
            base_output_dir: The base directory where results subdirectories (csv, gtf, fasta) will be created.
        """
        self.candidate_manager = candidate_manager
        self.target_gene_species = target_gene_species
        self.base_output_dir = base_output_dir
        logging.info("ResultsGenerator initialized.")

    def _get_output_path(self, 
                         sub_dir_name: str, 
                         file_identifier: str, # E.g., gene_id or a custom prefix
                         k_mer_length: Optional[int] = None,
                         extension: str = ".txt") -> str:
        """Helper to construct full output paths within standardized subdirectories."""
        results_sub_dir = os.path.join(self.base_output_dir, "results", sub_dir_name)
        os.makedirs(results_sub_dir, exist_ok=True)
        
        filename_parts = [file_identifier]
        if k_mer_length is not None:
            filename_parts.append(f"{k_mer_length}mers")
        
        filename = "_".join(filename_parts) + extension
        return os.path.join(results_sub_dir, filename)

    def generate_csv_report(self, 
                            csv_filename_prefix: Optional[str] = None,
                            off_target_multiplicities: Optional[Dict[str, int]] = None,
                            include_transcript_ids: bool = False,
                            include_exon_ids: bool = False
                            ) -> str:
        """
        Generates a CSV report for all candidate targets.

        Args:
            gene_id: The ID of the target gene (for filename and context).
            k_mer_length: The k-mer length used (for filename).
            off_target_multiplicities: Optional dict mapping candidate ID (e.g., S000001) to 
                                       its count of off-target sites (from a separate analysis).
            csv_filename_prefix: Optional prefix for the CSV filename. If None, gene_id is used.
            include_transcript_ids: If True, include a comma-separated list of transcript IDs.
            include_exon_ids: If True, include a comma-separated list of exon IDs.

        Returns:
            The path to the generated CSV file.
        """
        target_gene = self.candidate_manager.target_gene
        logging.info(f"Generating CSV report for gene {target_gene.gene_id}.")
        
        if off_target_multiplicities is None:
            off_target_multiplicities = {}

        results_data = []
        all_candidates = self.candidate_manager.get_all_candidate_targets()
        
        total_transcripts_in_gene = len(self.candidate_manager.target_gene.transcripts) if self.candidate_manager.target_gene.transcripts else 0

        for candidate in all_candidates.values():
            chrom_pos = candidate.chromosomal_position
            # Ensure chrom_pos is not None before trying to strip
            position_without_strand = chrom_pos.rstrip(':+-') if chrom_pos else ""
            # Construct Ensembl link based on species
            # Modify if species format is different (e.g. Mus_musculus)
            ensembl_base_url = f"https://www.ensembl.org/{self.target_gene_species.capitalize()}/Location/View?r=" 
            if "GRCz" in self.target_gene_species: # Zebrafish example
                 ensembl_base_url = f"https://www.ensembl.org/Danio_rerio/Location/View?r=" 
            
            ensembl_link = f"{ensembl_base_url}{position_without_strand}" if position_without_strand else ""

            oligo_rc_seq = str(Seq(candidate.sequence).reverse_complement()) if candidate.sequence else ""

            transcript_count = len(candidate.transcripts) if candidate.transcripts else 0
            transcript_prevalence = round(transcript_count / total_transcripts_in_gene, 3) if total_transcripts_in_gene > 0 else 0
            
            record = {
                'candidate_id': candidate.id,
                'target_sequence': candidate.sequence,
                'chromosomal_position': candidate.chromosomal_position,
                'oligo_reverse_complement': oligo_rc_seq,
                'oligo_GC_percent': gc_fraction(oligo_rc_seq.upper()) if oligo_rc_seq else 0.0,
                'oligo_AT_run': longest_at_run(oligo_rc_seq) if oligo_rc_seq else 0,
                'oligo_T_run': longest_t_run(oligo_rc_seq) if oligo_rc_seq else 0,
                'repeated_sites_count': len(candidate.repeated_sites),
                'off_target_count': off_target_multiplicities.get(candidate.id, 0),
                'dG_binding_target': candidate.dG_binding,
                'oligo_homodimer_dG': candidate.oligo_homodimer_dG,
                'pedersen_steady_state_pct': candidate.pedersen_steady_state,
                'transcript_prevalence_ratio': transcript_prevalence,
                'ensembl_link': ensembl_link,
            }

            if include_transcript_ids:
                record['transcript_ids'] = ",".join(sorted([t.transcript_id for t in candidate.transcripts])) if candidate.transcripts else ""
            if include_exon_ids:
                record['exon_ids'] = ",".join(sorted(list(set([e.exon_id for e in candidate.exons if e and e.exon_id])))) if candidate.exons else "" # Use set to ensure unique exon IDs

            results_data.append(record)

        if not results_data:
            logging.warning(f"No candidate data to write for CSV report for gene {target_gene.gene_id}.")
            # Create an empty file or a file with headers only, as per desired behavior
            # For now, let's still create the file path
            
        df = pl.DataFrame(results_data)
        
        file_identifier_prefix = csv_filename_prefix if csv_filename_prefix else target_gene.gene_id
        output_csv_path = self._get_output_path(
            sub_dir_name="csv_reports", 
            file_identifier=file_identifier_prefix, 
            k_mer_length=self.candidate_manager.k, 
            extension=".csv"
        )
        
        df.write_csv(output_csv_path)
        logging.info(f"CSV report generated at: {output_csv_path} with {len(df)} records.")
        return output_csv_path