import logging
import os
from typing import Optional, Tuple, List, Dict
import gzip # Import gzip

# Assuming Gene and Transcript are part of genome_utils or a similar accessible module
# Adjust the import based on your actual structure for Gene and Transcript classes
try:
    from src.utils.genome_utils import Genome, Gene
except ImportError:
    logging.warning("genome_utils.Gene or not found, using placeholder. Functionality might be limited.")
    # Placeholder if Gene class is not directly importable for type hinting
    class Gene: pass 


from src.utils.file_operations import GenomeDownloader

class GenomeDataManager:
    def __init__(self,
                 gene_id: str,
                 species: str,
                 e_release: int,
                 genome_assembly: int,
                 genome_dir: str,
                 tsl_config_str: Optional[str] = None,
                 # scaffold_gtf_file_name: Optional[str] = None # Assuming downloader handles this
                 ):
        """
        Manages downloading, processing, and providing paths to essential genome data files.
        """
        self.gene_id = gene_id
        self.species = species
        self.e_release = e_release
        self.genome_assembly = genome_assembly
        self.genome_dir = genome_dir

        logging.info(f"Initializing GenomeDataManager for gene: {self.gene_id}, species: {self.species}, release: {self.e_release}")

        self.tsl_is_active, self.tsl_list_to_keep = self._convert_tsl_list(tsl_config_str) if tsl_config_str else (False, None)
        if self.tsl_is_active:
            logging.info(f"TSL filtering is active. Levels to keep: {self.tsl_list_to_keep}")
        else:
            logging.info("TSL filtering is not active or all levels are included.")

        # 1. Download base files using GenomeDownloader
        downloader = GenomeDownloader(
            species=self.species,
            e_release=self.e_release,
            genome_dir=self.genome_dir,
        )
        # These paths are to the raw downloaded files as returned by GenomeDownloader
        self.raw_gtf_path, self.raw_cdna_path, self.raw_genome_path, self.raw_scaffold_gtf_path = downloader.download()

        # 2. Initialize Genome objects
        # Construct reference name for genome-utils
        # Example: GRCm38 for mus_musculus, GRCh38 for homo_sapiens
        if self.species.lower() == "mus_musculus":
            reference_prefix = "GRCm"
        elif self.species.lower() == "homo_sapiens":
            reference_prefix = "GRCh"
        else:
            # Fallback or error for other species, assuming genome-utils needs this convention
            reference_prefix = f"GRC{self.species[0].upper()}" 
            logging.warning(f"Species '{self.species}' is not 'mus_musculus' or 'homo_sapiens'. Using prefix '{reference_prefix}'. Ensure this matches genome-utils expectations.")
        
        self.main_reference_name = f'{reference_prefix}{self.genome_assembly}'

        self.genome = Genome(
            reference_name=self.main_reference_name,
            annotation_version=str(self.e_release), # genome-utils might expect string
            gtf_path=self.raw_gtf_path,
            transcript_fasta_paths=self.raw_cdna_path,
            primary_assembly_path=self.raw_genome_path,
            tsl_to_keep=self.tsl_list_to_keep if self.tsl_is_active else None,
            protein_coding_only=True,
        )
        # Index the genome object after initialization (will apply TSL filtering from GTF)
        self.genome.index()
        logging.info(f"Main genome ('{self.main_reference_name}') indexed. Found {len(self.genome.genes)} genes.")

        self.genome_scaffolds: Optional[Genome] = None
        if self.raw_scaffold_gtf_path:
            # Assuming scaffold reference name might be different or need a suffix
            scaffold_reference_name = f'{self.main_reference_name}_scaffolds' 
            self.genome_scaffolds = Genome(
                reference_name=scaffold_reference_name,
                gtf_path=self.raw_scaffold_gtf_path,
            )
            self.genome_scaffolds.index(overwrite=False)
            logging.info(f"Scaffold genome ('{scaffold_reference_name}') indexed.")

        self.target_gene: Gene = self.genome.gene_by_id(self.gene_id)
        if not self.target_gene:
            # Try scaffolds if not in primary assembly, though typically genes are on primary
            if self.genome_scaffolds:
                logging.warning(f"Target gene {self.gene_id} not found in primary assembly, checking scaffolds...")
                self.target_gene = self.genome_scaffolds.gene_by_id(self.gene_id)
            if not self.target_gene: # Still not found
                raise ValueError(f"Target gene {self.gene_id} not found in the main or scaffold genome assemblies.")
        logging.info(f"Target gene '{self.target_gene.gene_name if hasattr(self.target_gene, 'gene_name') else self.gene_id}' loaded.")

        # --- File path attributes for prepared files will be populated by _prepare_xxx methods ---
        self.processed_cdna_path: str = self.raw_cdna_path
        self.cdna_excluding_target_path: Optional[str] = None
        self.gene_only_pre_mrna_fasta_path: Optional[str] = None
        self.other_genes_pre_mrna_fasta_path: Optional[str] = None
        
        # --- Run preparation methods ---
        self._prepare_tsl_filtered_cdna()       # Sets self.processed_cdna_path
        self._prepare_pre_mrna_fastas()         # Sets pre-mRNA paths and loads target gene pre-mRNA sequence
        self._prepare_cdna_excluding_target()   # Sets self.cdna_excluding_target_path

        logging.info("GenomeDataManager initialization complete.")

    def _convert_tsl_list(self, tsl_str: str) -> Tuple[bool, Optional[List[Optional[int]]]]:
        """
        Convert a string of transcript support levels into a list of integers or None values.
        
        Args:
            tsl_str (str): Comma-separated string of transcript support levels (e.g., "tsl1,tsl2,tslNA")
            
        Returns:
            Tuple[bool, Optional[List[Optional[int]]]]: A tuple containing:
                - bool: True if specific TSLs were provided, False if all TSLs are included
                - Optional[List[Optional[int]]]: List of TSL values (1-5 or None for NA)
        """
        tsl_tokens = [token.strip() for token in tsl_str.split(',') if token.strip()]
        converted_tsls = []

        for token in tsl_tokens:
            if token.lower().startswith("tsl"):
                value_part = token[3:]
                if value_part.lower() == "na":
                    converted_tsls.append(None)
                else:
                    try:
                        converted_tsls.append(int(value_part))
                    except ValueError:
                        logging.warning("Invalid transcript support level '%s'; using None.", token)
                        converted_tsls.append(None)
            else:
                try:
                    converted_tsls.append(int(token))
                except ValueError:
                    logging.warning("Invalid transcript support level '%s'; using None.", token)
                    converted_tsls.append(None)

        all_tsls = [1, 2, 3, 4, 5, None]
        if converted_tsls == all_tsls:
            return False, None
        return True, converted_tsls
    
    
    def _prepare_tsl_filtered_cdna(self):
        """
        If TSL filtering is active, this method now primarily ensures a TSL-filtered
        cDNA FASTA file is written out if needed, using the already TSL-filtered
        transcripts from the Genome object.
        It updates self.processed_cdna_path to point to this (potentially new) file.
        The Genome object itself is ALREADY filtered by TSL upon initialization if tsl_is_active.
        """
        if not self.tsl_is_active:
            self.processed_cdna_path = self.raw_cdna_path
            return

        
        base_raw_cdna_name = os.path.basename(self.raw_cdna_path)
        tsl_suffix = f".tsl{'_'.join(str(tsl) if tsl is not None else 'NA' for tsl in self.tsl_list_to_keep)}"
        
        if base_raw_cdna_name.endswith(".fa.gz"):
            tsl_filtered_fasta_name = base_raw_cdna_name.replace(".fa.gz", f"{tsl_suffix}.fa.gz")
        elif base_raw_cdna_name.endswith(".fasta.gz"):
            tsl_filtered_fasta_name = base_raw_cdna_name.replace(".fasta.gz", f"{tsl_suffix}.fasta.gz")
        elif base_raw_cdna_name.endswith(".fa"):
            tsl_filtered_fasta_name = base_raw_cdna_name.replace(".fa", f"{tsl_suffix}.fa")
        elif base_raw_cdna_name.endswith(".fasta"):
            tsl_filtered_fasta_name = base_raw_cdna_name.replace(".fasta", f"{tsl_suffix}.fasta")
        else:
            tsl_filtered_fasta_name = f"{base_raw_cdna_name}{tsl_suffix}.fasta"
            logging.warning(f"Raw cDNA path '{self.raw_cdna_path}' has unknown FASTA extension. Outputting TSL-filtered as '{tsl_filtered_fasta_name}'")

        potential_path = os.path.join(self.genome_dir, tsl_filtered_fasta_name)

        if os.path.exists(potential_path) and os.path.getsize(potential_path) > 0:
            logging.info(f"TSL-filtered cDNA FASTA already exists: {potential_path}")
            self.processed_cdna_path = potential_path
            # Update Genome's transcript fasta path to the filtered one and re-parse sequences from it.
            # This is important if the existing file should be the source of sequences.
            if self.genome:
                self.genome.transcript_fasta_paths = [self.processed_cdna_path]
                logging.info(f"Genome object will use existing TSL-filtered FASTA: {self.processed_cdna_path} for transcript sequences.")
                self.genome._parse_transcript_fasta() # Re-parse sequences from this specific file
            return
        
        logging.info("Preparing TSL-filtered cDNA FASTA output file.")

        count_written = 0
        try:
            open_func = gzip.open if potential_path.endswith(".gz") else open
            mode = 'wt' if potential_path.endswith(".gz") else 'w'
            with open_func(potential_path, mode) as f_out:
                # Iterate TSL-filtered transcripts from the already filtered Genome object
                # The Genome object's transcripts are already filtered by TSL during its initialization.
                for transcript in self.genome.transcripts: # These are already TSL and biotype filtered
                    # We still need to ensure the transcript sequence is loaded from the *raw* cDNA
                    # if it hasn't been, before writing. The genome.index() called earlier handles this.
                    if transcript.sequence:
                        f_out.write(f">{transcript.transcript_id}\n{transcript.sequence}\n")
                        count_written += 1
                    else:
                        # This case implies the transcript was in the GTF (and passed TSL/biotype filters)
                        # but its sequence was not found in the raw_cdna_path.
                        logging.debug(f"Transcript {transcript.transcript_id} (gene {transcript.gene_id}) passed GTF filters but has no sequence from {self.raw_cdna_path}. Not written to TSL-filtered FASTA.")
                        
            
            if count_written > 0:
                self.processed_cdna_path = potential_path
                logging.info(f"TSL-filtered cDNA FASTA created with {count_written} transcripts: {self.processed_cdna_path}")
                
                
            else:
                logging.warning(f"TSL filtering active, but no transcripts were written to {potential_path}. "
                                "This might be due to no transcripts passing filters or sequences not found in raw cDNA. "
                                f"Processed cDNA path remains {self.raw_cdna_path}.")
                self.processed_cdna_path = self.raw_cdna_path
                
        except Exception as e:
            logging.error(f"Error during TSL filtering of cDNA: {e}. Processed cDNA path set to raw path: {self.raw_cdna_path}.")
            self.processed_cdna_path = self.raw_cdna_path
            if self.genome:
                self.genome.transcript_fasta_paths = [self.raw_cdna_path] # Ensure it points to raw
                logging.info("Reverting Genome object to use raw cDNA path for transcript sequences due to error.")
                self.genome._parse_transcript_fasta()


    def _prepare_pre_mrna_fastas(self):
        """
        Prepares two pre-mRNA FASTA files: one for the target gene only,
        and one for all other genes. Also loads pre-mRNA for the target gene object.
        """
        logging.info(f"Preparing pre-mRNA FASTA files for gene '{self.gene_id}' and other genes.")

        # 1. Target gene's pre-mRNA
        # Ensure .fa extension, genome-utils might handle .gz internally if input path has it
        gene_only_fasta_name = f"{self.main_reference_name}.premrna.{self.gene_id}.fa" 
        self.gene_only_pre_mrna_fasta_path = os.path.join(self.genome_dir, gene_only_fasta_name)
        
        try:
            target_pre_mrna_sequences = self.genome.extract_premrna_sequences_per_gene(
                gene_ids=[self.gene_id],
                output_path=self.gene_only_pre_mrna_fasta_path
            )
            if self.gene_id in target_pre_mrna_sequences and hasattr(self.target_gene, 'pre_mrna_sequence'):
                self.target_gene.pre_mrna_sequence = target_pre_mrna_sequences[self.gene_id]
                logging.info(f"Target gene ('{self.gene_id}') pre-mRNA sequence loaded and FASTA saved to: {self.gene_only_pre_mrna_fasta_path}")
            elif self.gene_id not in target_pre_mrna_sequences:
                 logging.error(f"Could not extract pre-mRNA sequence data for target gene {self.gene_id} from extract_premrna_sequences_per_gene return.")
            else: # sequence data present, but target_gene object has no attribute
                 logging.warning(f"Target gene object for {self.gene_id} does not have 'pre_mrna_sequence' attribute to assign to.")

        except Exception as e:
            logging.error(f"Error extracting pre-mRNA for target gene {self.gene_id}: {e}")
            self.gene_only_pre_mrna_fasta_path = None # Indicate failure

        # 2. Other genes' pre-mRNA (all genes excluding the target gene)
        other_genes_fasta_name = f"{self.main_reference_name}.premrna.all_except_{self.gene_id}.fa"
        self.other_genes_pre_mrna_fasta_path = os.path.join(self.genome_dir, other_genes_fasta_name)
        
        try:
            # Assuming extract_genome_premrna_sequences writes to output_path and excludes specified genes
            self.genome.extract_genome_premrna_sequences(
                output_path=self.other_genes_pre_mrna_fasta_path,
                exclude_genes=[self.gene_id] 
            )
            logging.info(f"Pre-mRNA FASTA (excluding '{self.gene_id}') saved to: {self.other_genes_pre_mrna_fasta_path}")
        except Exception as e:
            logging.error(f"Error extracting pre-mRNA for other genes: {e}")
            self.other_genes_pre_mrna_fasta_path = None # Indicate failure

    def _prepare_cdna_excluding_target(self):
        """
        Creates a cDNA FASTA file that includes all transcripts *except* those from the target gene.
        Uses the (potentially TSL-filtered) self.processed_cdna_path as the reference for transcript sequences.
        """
        
        target_gene_transcript_ids = {t.transcript_id for t in self.target_gene.transcripts if hasattr(t, 'transcript_id')}
        
        # Simplify name generation and ensure .gz is preserved if input was gzipped
        input_is_gzipped = self.processed_cdna_path.endswith(".gz")
        name_part = os.path.basename(self.processed_cdna_path)
        if input_is_gzipped:
            name_part = name_part[:-3] # Remove .gz
        
        if name_part.endswith(".fa"):
            name_part = name_part[:-3]
            ext = ".fa.gz" if input_is_gzipped else ".fa"
        elif name_part.endswith(".fasta"):
            name_part = name_part[:-6]
            ext = ".fasta.gz" if input_is_gzipped else ".fasta"
        else: # Fallback, just append
            ext = ".fa.gz" if input_is_gzipped else ".fa"

        cdna_excluding_target_fasta_name = f"{name_part}_no_{self.gene_id}{ext}"
        self.cdna_excluding_target_path = os.path.join(self.genome_dir, cdna_excluding_target_fasta_name)

        # Check if file already exists
        if os.path.exists(self.cdna_excluding_target_path) and os.path.getsize(self.cdna_excluding_target_path) > 0:
            logging.info(f"cDNA FASTA excluding target gene already exists: {self.cdna_excluding_target_path}")
            return
        
        logging.info(f"Preparing cDNA FASTA excluding target gene: {self.gene_id}, using input: {self.processed_cdna_path}")

        count_written = 0
        try:
            open_func_out = gzip.open if self.cdna_excluding_target_path.endswith(".gz") else open
            mode_out = 'wt' if self.cdna_excluding_target_path.endswith(".gz") else 'w'

            with open_func_out(self.cdna_excluding_target_path, mode_out) as f_out:
                # Iterate all transcripts from the main genome object.
                # These sequences come directly from the Genome object, which should have handled
                # the TSL filtering if self.processed_cdna_path was updated and genome re-indexed.
                for transcript in self.genome.transcripts:
                    if transcript.transcript_id in target_gene_transcript_ids:
                        continue 
                    
                    # The TSL check here is a safeguard. Ideally, if the genome was re-indexed with
                    # a TSL-filtered FASTA, self.genome.transcripts or iterating its IDs would only yield
                    # TSL-passing transcripts. If not re-indexed, this check is necessary.
                    if transcript and hasattr(transcript, 'sequence') and transcript.sequence:
                        passes_tsl = True # Assume passes unless TSL is active and it fails
                        if self.tsl_is_active and self.tsl_list_to_keep: 
                            if not (hasattr(transcript, 'support_level') and transcript.support_level in self.tsl_list_to_keep):
                                passes_tsl = False

                        if passes_tsl:
                            f_out.write(f">{transcript.transcript_id}\n{transcript.sequence}\n")
                            count_written += 1
            
            if count_written > 0:
                logging.info(f"Created cDNA FASTA excluding target gene '{self.gene_id}' with {count_written} transcripts: {self.cdna_excluding_target_path}")
            else:
                logging.warning(f"No transcripts written to cDNA FASTA excluding target gene '{self.gene_id}'. File might be empty: {self.cdna_excluding_target_path}")

        except Exception as e:
            logging.error(f"Error creating cDNA FASTA excluding target gene: {e}")
            self.cdna_excluding_target_path = None


    # --- Getter methods ---
    def get_target_gene_object(self) -> Gene:
        return self.target_gene

    def get_main_genome_object(self) -> Genome:
        return self.genome

    def get_scaffold_genome_object(self) -> Optional[Genome]:
        return self.genome_scaffolds

    def get_processed_cdna_path(self) -> str:
        """Path to cDNA FASTA, potentially TSL-filtered."""
        return self.processed_cdna_path

    def get_cdna_excluding_target_path(self) -> Optional[str]:
        """Path to cDNA FASTA excluding target gene's transcripts."""
        return self.cdna_excluding_target_path

    def get_gene_only_pre_mrna_fasta_path(self) -> Optional[str]:
        """Path to pre-mRNA FASTA for only the target gene."""
        return self.gene_only_pre_mrna_fasta_path

    def get_other_genes_pre_mrna_fasta_path(self) -> Optional[str]:
        """Path to pre-mRNA FASTA for all genes excluding the target."""
        return self.other_genes_pre_mrna_fasta_path
    
    def get_raw_download_paths(self) -> Dict[str, Optional[str]]:
        return {
            "gtf": self.raw_gtf_path,
            "cdna": self.raw_cdna_path,
            "genome": self.raw_genome_path,
            "scaffold_gtf": self.raw_scaffold_gtf_path
        } 