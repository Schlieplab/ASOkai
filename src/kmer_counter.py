import os
import subprocess
import tempfile
import gzip
import logging
import shutil
from typing import Dict, List, Set, Tuple, Optional, Iterable, Any
import concurrent.futures
import threading

from .utils import ProgressTracker
import polars as pl
import ahocorasick

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Globals for worker processes ---
# These will be populated by the initializer
worker_automatons: List[ahocorasick.Automaton] = []
worker_potential_kmers_by_aso: Dict[str, List[Tuple[str, float]]] = {}

def init_worker_ahocorasick(
    automatons: List[ahocorasick.Automaton],
    potential_kmers_by_aso: Dict[str, List[Tuple[str, float]]]
):
    """
    Initializer for each worker in the process pool.
    This function sets up the global read-only data structures for the worker.
    """
    global worker_automatons, worker_potential_kmers_by_aso
    worker_automatons = automatons
    worker_potential_kmers_by_aso = potential_kmers_by_aso
    logging.info(f"Worker process {os.getpid()} initialized.")

def _process_gene_for_matrix_worker(
    gene_id: str,
    gene_sequence: str,
    verbose: bool
) -> Tuple[str, Dict[str, int]]:
    """
    Processes a single gene using the globally available Aho-Corasick automatons.
    """
    try:
        gene_kmer_counts: Dict[str, int] = {}
        for automaton in worker_automatons:
            for _, kmer in automaton.iter(gene_sequence):
                gene_kmer_counts[kmer] = gene_kmer_counts.get(kmer, 0) + 1

        aso_counts_for_gene: Dict[str, int] = {}
        for aso_id, kmer_list in worker_potential_kmers_by_aso.items():
            total_count = sum(gene_kmer_counts.get(kmer_seq, 0) for kmer_seq, _ in kmer_list)
            aso_counts_for_gene[aso_id] = total_count
        
        if verbose:
            if sum(aso_counts_for_gene.values()) > 0:
                logging.info(f"[Gene: {gene_id}] Processed. Found hits for {sum(1 for x in aso_counts_for_gene.values() if x > 0)} ASOs.")
        
        return gene_id, aso_counts_for_gene

    except Exception as e:
        logging.error(f"[Gene: {gene_id}, Worker: {os.getpid()}] Error during chunked Aho-Corasick processing: {e}")
        return gene_id, {aso_id: 0 for aso_id in worker_potential_kmers_by_aso.keys()}

class CommandRunner:
    """Handles execution of shell commands."""
    def run(self, cmd: List[str], work_dir: Optional[str] = None, check: bool = True) -> subprocess.CompletedProcess:
        logging.debug(f"Running command: {' '.join(cmd)} in {work_dir or os.getcwd()}")
        try:
            process = subprocess.run(cmd, capture_output=True, text=True, check=check, cwd=work_dir)
            if process.stdout:
                logging.debug(f"Command stdout: {process.stdout.strip()}")
            if process.stderr:
                # KMC often outputs progress to stderr, so log as debug unless check=True and it fails
                log_level = logging.ERROR if check and process.returncode != 0 else logging.DEBUG
                logging.log(log_level, f"Command stderr: {process.stderr.strip()}")
            return process
        except subprocess.CalledProcessError as e:
            logging.error(f"Command '{' '.join(e.cmd)}' failed with exit code {e.returncode}.")
            logging.error(f"Stdout: {e.stdout.strip()}")
            logging.error(f"Stderr: {e.stderr.strip()}")
            raise
        except FileNotFoundError:
            logging.error(f"Command not found: {cmd[0]}. Ensure it is installed and in PATH.")
            raise

class KMCDatabase:
    """Represents a KMC database and manages its lifecycle."""
    def __init__(self, db_prefix_path: str, k_value: int):
        self.db_prefix_path = os.path.abspath(db_prefix_path)
        self.k_value = k_value
        
        db_dir = os.path.dirname(self.db_prefix_path)
        if db_dir: # Create if db_prefix_path includes a directory path part
            os.makedirs(db_dir, exist_ok=True)

    def get_prefix_path(self) -> str:
        """Returns the absolute database prefix path."""
        return self.db_prefix_path

    def get_k(self) -> int:
        """Returns the k-mer length of the database."""
        return self.k_value


    def exists(self) -> bool:
        """Checks if the database files (.kmc_pre, .kmc_suf) exist."""
        pre_file = f"{self.db_prefix_path}.kmc_pre"
        suf_file = f"{self.db_prefix_path}.kmc_suf"
        return os.path.exists(pre_file) and os.path.exists(suf_file)

    def __del__(self) -> None:
        """Deletes the KMC database files (.kmc_pre, .kmc_suf) and then deletes the object."""
        logging.debug(f"Attempting to delete KMC database files for prefix: {self.db_prefix_path}")
        for suffix in [".kmc_pre", ".kmc_suf"]:
            f_path = self.db_prefix_path + suffix
            if os.path.exists(f_path):
                try:
                    os.remove(f_path)
                    logging.debug(f"Deleted KMC db file: {f_path}")
                except OSError as e:
                    logging.warning(f"Error deleting KMC db file {f_path}: {e}")
        del self


class KMC:
    """Wrapper for KMC (K-mer Counter) executable."""
    def __init__(self, 
                 kmc_path: str, 
                 default_threads: int = 1, 
                 default_memory_gb: int = 4,
                 verbose: bool = False):
        if not shutil.which(kmc_path):
            
            if not (os.path.isfile(kmc_path) and os.access(kmc_path, os.X_OK)):
                 raise FileNotFoundError(f"KMC executable not found or not executable at: {kmc_path}")
        self.kmc_path = os.path.abspath(kmc_path) if not shutil.which(kmc_path) else kmc_path
        self.default_threads = default_threads
        self.default_memory_gb = default_memory_gb
        self.verbose = verbose
        self.runner = CommandRunner()

    def build_database(self,
                       input_path: str,
                       db_prefix_path: str,
                       k_value: int,
                       temp_dir_path: str,
                       input_type: str = "fm", 
                       min_count: int = 1,
                       threads: Optional[int] = None,
                       memory_gb: Optional[int] = None,
                       additional_args: Optional[List[str]] = None) -> KMCDatabase:
        """
        Builds a KMC database.
        Args:
            input_path: Path to input file (FASTA/FASTQ).
            db_prefix_path: Prefix for the output KMC database files.
            k_value: K-mer length.
            temp_dir_path: Path to the temporary directory for KMC.
            input_type: input in FASTA format (-fa), FASTQ format (-fq), multi FASTA (-fm) or BAM (-fbam) or KMC (-fkmc); default: multi FASTA.
            min_count: Minimum count for k-mers to be stored (-ci).
            threads: Number of threads to use. Defaults to self.default_threads.
            memory_gb: Memory in GB to use. Defaults to self.default_memory_gb.
            additional_args: List of any other KMC arguments. (Should be in kmc arguments format, e.g. ['-ci10'])
        Returns:
            A KMCDatabase object representing the built database.
        """
        resolved_threads = threads if threads is not None else self.default_threads
        resolved_memory_gb = memory_gb if memory_gb is not None else self.default_memory_gb

        # Create KMCDatabase instance before building
        kmc_db = KMCDatabase(db_prefix_path=db_prefix_path, k_value=k_value)

        cmd = [
            self.kmc_path,
            f"-k{k_value}",
            f"-{input_type}", # -fm (auto), -fa (fasta), -fq (fastq)
            f"-t{resolved_threads}",
            f"-m{resolved_memory_gb}",
            f"-ci{min_count}",
        ]
        if additional_args:
            cmd.extend(additional_args)
        
        cmd.extend([input_path, kmc_db.get_prefix_path(), temp_dir_path])
        
        if self.verbose:
            logging.info(f"Building KMC database from {input_path} with k={k_value}...")
        self.runner.run(cmd, work_dir=temp_dir_path)
        if self.verbose:
            logging.info(f"KMC database built at {kmc_db.get_prefix_path()}")
        return kmc_db
    
    

class KMCTools:
    """Wrapper for KMC_Tools executable."""
    def __init__(self, kmc_tools_path: str):
        if not shutil.which(kmc_tools_path):
            raise FileNotFoundError(f"KMC_Tools executable not found at: {kmc_tools_path}")
        self.kmc_tools_path = kmc_tools_path
        self.runner = CommandRunner()
        
    def simple_operation(self,
                         left_db: KMCDatabase,
                         right_db: KMCDatabase,
                         operation: str,
                         output_db_prefix: str,
                         work_dir: Optional[str] = None,
                         additional_args: Optional[List[str]] = None,) -> KMCDatabase:
        """
        Performs a simple operation (like intersect, union) between two KMC databases.
        Args:
            left_db: The first (left) input KMC database object.
            right_db: The second (right) input KMC database object.
            operation: The operation to perform (e.g., 'intersect').
            output_db_prefix: Prefix for the output KMC database files.
            work_dir: Working directory for the command.
            additional_args: List of any other kmc_tools simple arguments.
        Returns:
            A KMCDatabase object representing the output database.
        """
        if left_db.get_k() != right_db.get_k():
            logging.error(
                f"K-values of input databases for '{operation}' differ: "
                f"{left_db.get_prefix_path()} (k={left_db.get_k()}) and "
                f"{right_db.get_prefix_path()} (k={right_db.get_k()}). "
            )
            raise ValueError(
                f"K-values of input databases for '{operation}' differ: "
                f"{left_db.get_prefix_path()} (k={left_db.get_k()}) and "
                f"{right_db.get_prefix_path()} (k={right_db.get_k()}). "
            )

        output_k_value = left_db.get_k()
        output_kmc_db = KMCDatabase(db_prefix_path=output_db_prefix, k_value=output_k_value)

        cmd = [
            self.kmc_tools_path, 
            'simple', 
            left_db.get_prefix_path(), 
            right_db.get_prefix_path(), 
            operation, 
            output_kmc_db.get_prefix_path()
        ]
        if additional_args:
            cmd.extend(additional_args)
        self.runner.run(cmd, work_dir=work_dir)
        return output_kmc_db

    def transform_database(self,
                           input_db: KMCDatabase,
                           operation: str, 
                           output_path: Optional[str] = None,
                           work_dir: Optional[str] = None,
                           additional_args: Optional[List[str]] = None) -> None:
        """
        Transforms a KMC database (e.g., dumps k-mers and counts).
        Args:
            input_db: The input KMC database object.
            operation: The transformation operation (e.g., 'dump').
            output_path: Path for the output file (e.g., for dump operation).
            work_dir: Working directory for the command.
            additional_args: List of any other kmc_tools transform arguments.
        """
        cmd = [self.kmc_tools_path, 'transform', input_db.get_prefix_path(), operation]
        if output_path: # Some operations like dump require an output path directly in command
             cmd.extend(['-s', output_path]) # Assume -s for sorted dump, adjust if needed
        if additional_args:
            cmd.extend(additional_args)
        
        self.runner.run(cmd, work_dir=work_dir)

class KmerDbQuerier:
    """Encapsulates logic for querying a KMC database for counts of specific k-mers."""
    def __init__(self, kmc_executor: KMC, kmc_tools_executor: KMCTools, k: int):
        self.kmc_executor = kmc_executor
        self.kmc_tools_executor = kmc_tools_executor
        self.k = k

    def get_counts(self, main_kmc_db: KMCDatabase, target_kmers: Set[str], temp_dir: str) -> Dict[str, int]:
        """
        Queries a KMC database for counts of specific target k-mers.
        Args:
            main_kmc_db: The KMC database object to query.
            target_kmers: A set of k-mer sequences to query.
            temp_dir: Temporary directory to write intermediate files.
        Returns:
            A dictionary mapping k-mer sequences to their counts.
        """
        if not target_kmers:
            return {}

        target_kmers_fasta_file = os.path.join(temp_dir, "query_target_kmers.fasta")
        with open(target_kmers_fasta_file, 'w') as f:
            for i, kmer in enumerate(target_kmers):
                f.write(f">query_kmer_{i}\n{kmer}\n")

        target_kmers_db_path_prefix = os.path.join(temp_dir, "query_target_kmers_db")
        target_kmers_db = self.kmc_executor.build_database(
            input_path=target_kmers_fasta_file,
            db_prefix_path=target_kmers_db_path_prefix,
            k_value=self.k,
            temp_dir_path=temp_dir,
            input_type="fm",
            min_count=1,
            threads=1, 
            memory_gb=2 
        )
        
        if main_kmc_db.get_k() != self.k:
             logging.error(f"K-value mismatch between main DB ({main_kmc_db.get_k()}) and target k-mers DB ({target_kmers_db.get_k()}) in get_counts.")
             del target_kmers_db
             raise ValueError(f"K-value mismatch between main DB ({main_kmc_db.get_k()}) and target k-mers DB ({target_kmers_db.get_k()}) in get_counts.")

        intersect_db_path_prefix = os.path.join(temp_dir, "query_intersect_db")
        
        intersect_db = self.kmc_tools_executor.simple_operation(
            left_db=main_kmc_db, 
            right_db=target_kmers_db,
            operation='intersect',
            output_db_prefix=intersect_db_path_prefix, 
            work_dir=temp_dir,
            additional_args=["-ocleft"] 
        )

        output_counts_file = os.path.join(temp_dir, "query_kmer_counts.txt")
        self.kmc_tools_executor.transform_database(
            input_db=intersect_db,
            operation='dump',
            output_path=output_counts_file,
            work_dir=temp_dir
        )
        
        kmer_counts: Dict[str, int] = {kmer: 0 for kmer in target_kmers}
        if os.path.exists(output_counts_file):
            with open(output_counts_file, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 2:
                        kmer, count_str = parts[0], parts[1]
                        if kmer in kmer_counts:
                           kmer_counts[kmer] = int(count_str)
                           
        os.remove(target_kmers_fasta_file)
        os.remove(output_counts_file)
        del target_kmers_db, intersect_db
        
        return kmer_counts

class KmerCounter:
    """
    Orchestrates k-mer counting workflows using KMC tools, KMC and KMCTools.
    """

    def __init__(self,
                 k: int,
                 kmc_path: str = "kmc",
                 kmc_tools_path: str = "kmc_tools",
                 kmc_db_threads: int = 4,
                 kmc_db_memory_gb: int = 12,
                 gene_processing_workers: int = os.cpu_count() or 1,
                 temp_dir_base: Optional[str] = None,
                 kmc_min_count: int = 1,
                 verbose: bool = False):
        """
        Initializes the KmerCounter.

        Args:
            k: The k-mer length.
            kmc_path: Path to the KMC executable.
            kmc_tools_path: Path to the KMC_Tools executable.
            kmc_db_threads: Number of threads for KMC database creation.
            kmc_db_memory_gb: Memory (in GB) for KMC database creation.
            gene_processing_workers: Number of worker threads for per-gene processing.
            temp_dir_base: Optional base directory for temporary files. If None,
                           the system's default temporary directory is used.
            kmc_min_count: Minimum count for k-mers to be stored by KMC (-ci).
            verbose: Enable verbose logging.
        """
        self.k = k
        self.verbose = verbose
        self.kmc_path = kmc_path
        self.kmc_tools_path = kmc_tools_path
        self.kmc_db_threads = kmc_db_threads
        self.kmc_db_memory_gb = kmc_db_memory_gb
        self.gene_processing_workers = gene_processing_workers
        self.temp_dir_base = temp_dir_base or os.path.join(os.getcwd(), 'temp')
        self.kmc_min_count = kmc_min_count

        os.makedirs(self.temp_dir_base, exist_ok=True)

        self.kmc = KMC(self.kmc_path, self.kmc_db_threads, self.kmc_db_memory_gb, False)
        self.kmc_tools = KMCTools(self.kmc_tools_path)
        self.runner = CommandRunner()
        self.db_querier = KmerDbQuerier(self.kmc, self.kmc_tools, self.k)

        self._lock = threading.Lock()
        self._shutdown = threading.Event()
        self._temp_dirs_to_clean: List[str] = []

        if self.verbose:
            logging.info(f"KmerCounter initialized with k={k}.")

    def find_present_targets(self, fasta_path: str, candidate_sites_kmers: Dict[str, str]) -> List[str]:
        """
        Finds which candidate sites' k-mers exist in a given FASTA file.

        Args:
            fasta_path: Path to the FASTA file to search within.
            candidate_sites_kmers: A dictionary where keys are site IDs and values are k-mer strings.

        Returns:
            A list of site IDs that are found in the FASTA file.
        """
        if not os.path.exists(fasta_path):
            raise FileNotFoundError(f"FASTA file not found: {fasta_path}")

        if self.verbose:
            logging.info(f"Checking for existence of {len(candidate_sites_kmers)} candidate sites in {fasta_path}.")

        all_target_kmers = set(candidate_sites_kmers.values())
        for kmer_seq in all_target_kmers:
            if len(kmer_seq) != self.k:
                raise ValueError(
                    f"K-mer '{kmer_seq}' has length {len(kmer_seq)}, "
                    f"but k is set to {self.k}. All k-mers must have length k."
                )

        if not all_target_kmers:
            if self.verbose:
                logging.warning("No k-mers to check. Returning empty list.")
            return []

        main_temp_dir = tempfile.mkdtemp(dir=self.temp_dir_base)
        if self.verbose:
            logging.info(f"Created temporary directory for target search: {main_temp_dir}")

        global_kmc_db = None
        try:
            kmc_db_path_prefix = os.path.join(main_temp_dir, "search_kmc_db")

            global_kmc_db = self.kmc.build_database(
                input_path=fasta_path,
                db_prefix_path=kmc_db_path_prefix,
                k_value=self.k,
                temp_dir_path=main_temp_dir,
                input_type="fm",
                min_count=self.kmc_min_count,
                threads=self.kmc_db_threads,
                memory_gb=self.kmc_db_memory_gb
            )
            if self.verbose:
                logging.info(f"KMC database built at {global_kmc_db.get_prefix_path()}")

            if self.verbose:
                logging.info(f"Querying KMC database for {len(all_target_kmers)} unique k-mers...")
            all_kmer_counts = self.db_querier.get_counts(global_kmc_db, all_target_kmers, main_temp_dir)
            if self.verbose:
                logging.info("Finished querying KMC database.")

            present_site_ids = []
            for site_id, kmer_seq in candidate_sites_kmers.items():
                if all_kmer_counts.get(kmer_seq, 0) > 0:
                    present_site_ids.append(site_id)

            logging.info(f"Found {len(present_site_ids)} present sites out of {len(candidate_sites_kmers)} candidates.")
            return present_site_ids

        finally:
            if self.verbose:
                logging.info(f"Cleaning up temporary directory: {main_temp_dir}")
            if global_kmc_db:
                del global_kmc_db
            shutil.rmtree(main_temp_dir, ignore_errors=True)

    def calculate_aggregate_counts(self, pre_mrna_fasta_path: str, potential_kmers_by_aso: Dict[str, List[Tuple[str, float]]]) -> Dict[str, int]:
        """
        Calculates aggregate off-target counts for each ASO across the entire pre-mRNA FASTA file.

        Args:
            pre_mrna_fasta_path: Path to the gzipped pre-mRNA FASTA file.
            potential_kmers_by_aso: Dictionary mapping ASO IDs to a list of potential k-mer sequences.

        Returns:
            A dictionary mapping ASO IDs to their total k-mer counts.
        """
        if not os.path.exists(pre_mrna_fasta_path):
            raise FileNotFoundError(f"Pre-mRNA FASTA file not found: {pre_mrna_fasta_path}")

        if self.verbose:
            logging.info("Starting aggregate k-mer counting for all ASOs.")

        all_unique_potential_kmers = set()
        for kmer_list in potential_kmers_by_aso.values():
            for kmer_seq, ddg in kmer_list:
                if len(kmer_seq) != self.k:
                    raise ValueError(
                        f"K-mer '{kmer_seq}' has length {len(kmer_seq)}, "
                        f"but k is set to {self.k}. All potential k-mers must have the same length k."
                    )
                all_unique_potential_kmers.add(kmer_seq)
        
        aso_ids = list(potential_kmers_by_aso.keys())

        if not all_unique_potential_kmers:
            if self.verbose:
                logging.warning("No unique k-mers to count. Returning empty results.")
            return {aso_id: 0 for aso_id in aso_ids}

        main_temp_dir = tempfile.mkdtemp(dir=self.temp_dir_base)
        if self.verbose:
            logging.info(f"Created temporary directory for aggregate counts: {main_temp_dir}")
        total_secondary_sites_count = 0
        global_kmc_db = None
        try:
            kmc_db_path_prefix = os.path.join(main_temp_dir, "global_premrna_kmc_db")

            if self.verbose:
                logging.info(f"Building global KMC database from {pre_mrna_fasta_path}...")
            global_kmc_db = self.kmc.build_database(
                input_path=pre_mrna_fasta_path,
                db_prefix_path=kmc_db_path_prefix, 
                k_value=self.k,
                temp_dir_path=main_temp_dir,
                input_type="fm", 
                min_count=self.kmc_min_count,
                threads=self.kmc_db_threads, 
                memory_gb=self.kmc_db_memory_gb 
            )
            if self.verbose:
                logging.info(f"Global KMC database built at {global_kmc_db.get_prefix_path()}")

            if self.verbose:
                logging.info(f"Querying KMC database for {len(all_unique_potential_kmers)} unique k-mers...")
            all_kmer_counts = self.db_querier.get_counts(global_kmc_db, all_unique_potential_kmers, main_temp_dir)
            if self.verbose:
                logging.info("Finished querying KMC database.")

            aso_aggregate_counts: Dict[str, int] = {}
            for aso_id, kmer_list in potential_kmers_by_aso.items():
                total_count = 0
                for kmer_seq, _ in kmer_list:
                    total_count += all_kmer_counts.get(kmer_seq, 0)
                aso_aggregate_counts[aso_id] = total_count
                total_secondary_sites_count += total_count
            
            logging.info(f"{total_secondary_sites_count} secondary sites found in {pre_mrna_fasta_path}.")
            return aso_aggregate_counts

        finally:
            if self.verbose:
                logging.info(f"Cleaning up temporary directory: {main_temp_dir}")
            if global_kmc_db:
                del global_kmc_db
            shutil.rmtree(main_temp_dir, ignore_errors=True)

    def _parse_fasta(self, file_path: str) -> Iterable[Tuple[str, str, str]]:
        """
        Parses a gzipped FASTA file, yielding (raw_header, gene_id, sequence).
        Gene ID is extracted assuming format like >ENSG...|... or >ENSG...
        """
        open_func = gzip.open if file_path.endswith(".gz") else open
        try:
            with open_func(file_path, 'rt') as f:
                header = None
                sequence_parts = []
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith(">"):
                        if header and sequence_parts:
                            gene_id_part = header.split('|')[0].lstrip('>')
                            yield header, gene_id_part, "".join(sequence_parts)
                        header = line
                        sequence_parts = []
                    else:
                        if header: #Only collect sequence if a header has been seen
                            sequence_parts.append(line)
                if header and sequence_parts: # Yield the last sequence
                    gene_id_part = header.split('|')[0].lstrip('>')
                    yield header, gene_id_part, "".join(sequence_parts)
        except Exception as e:
            logging.error(f"Error parsing FASTA file {file_path}: {e}")
            raise

    def calculate_per_gene_counts_matrix(self, 
                                         pre_mrna_fasta_path: str, 
                                         potential_kmers_by_aso: Dict[str, List[Tuple[str, float]]], 
                                         total_genes_for_matrix: Optional[int]
                                         ) -> pl.DataFrame:
        """
        Calculates per-gene off-target counts, producing an ASO x Gene matrix.
        Returns:
            A polars.DataFrame with ASOs as rows, Genes as columns, and k-mer counts as values.
        """
        if not os.path.exists(pre_mrna_fasta_path):
            raise FileNotFoundError(f"Pre-mRNA FASTA file not found: {pre_mrna_fasta_path}")

        if self.verbose:
            logging.info("Starting per-gene k-mer counting for ASO x Gene matrix.")

        all_unique_potential_kmers = set()
        for kmer_list in potential_kmers_by_aso.values():
            for kmer_seq, _ in kmer_list:
                if len(kmer_seq) != self.k:
                    raise ValueError(
                        f"K-mer '{kmer_seq}' has length {len(kmer_seq)}, "
                        f"but k is set to {self.k}. All potential k-mers must have the same length k."
                    )
                all_unique_potential_kmers.add(kmer_seq)
        
        aso_ids = list(potential_kmers_by_aso.keys())
        if not all_unique_potential_kmers:
            logging.warning("No unique k-mers to count. Returning empty matrix.")
            return pl.DataFrame(schema={aso_id: pl.Int64 for aso_id in aso_ids}).transpose(include_header=True, header_column_name='ASO_ID', column_names=[])

        # Chunked Aho-Corasick Implementation
        num_kmers = len(all_unique_potential_kmers)
        # Aim for chunks of ~1M k-mers, adjust as needed.
        chunk_size = 1_000_000 
        num_chunks = (num_kmers + chunk_size - 1) // chunk_size
        
        kmer_list = list(all_unique_potential_kmers)
        automatons = []
        
        logging.info(f"Building {num_chunks} Aho-Corasick automatons for {num_kmers} k-mers...")
        for i in range(num_chunks):
            automaton = ahocorasick.Automaton()
            chunk = kmer_list[i*chunk_size:(i+1)*chunk_size]
            for kmer in chunk:
                automaton.add_word(kmer, kmer)
            automaton.make_automaton()
            automatons.append(automaton)
        logging.info("Aho-Corasick automatons built.")

        if not total_genes_for_matrix or total_genes_for_matrix == 0:
            logging.warning("total_genes_for_matrix not provided or is zero. Progress tracking for gene matrix calculation will be limited or disabled. Returning empty matrix.")
            return pl.DataFrame(schema={aso_id: pl.Int64 for aso_id in aso_ids}).transpose(include_header=True, header_column_name='ASO_ID', column_names=[])

        results_per_gene: Dict[str, Dict[str, int]] = {} 

        progress_tracker = ProgressTracker(total_items=total_genes_for_matrix, description="Processing genes for KMC matrix", update_interval=200)
        actual_genes_submitted_count = 0

        with concurrent.futures.ProcessPoolExecutor(
            max_workers=self.gene_processing_workers,
            initializer=init_worker_ahocorasick,
            initargs=(automatons, potential_kmers_by_aso)
        ) as executor:
            futures = []
            for raw_header, gene_id, gene_sequence in self._parse_fasta(pre_mrna_fasta_path):
                if not gene_id or not gene_sequence: 
                    logging.warning(f"Skipping invalid entry from FASTA: Header='{raw_header}'")
                    continue
                futures.append(executor.submit(_process_gene_for_matrix_worker, gene_id, gene_sequence, self.verbose))
                actual_genes_submitted_count += 1
            
            if actual_genes_submitted_count == 0:
                logging.warning("No valid genes found in FASTA to process after parsing. Returning empty matrix.")
                return pl.DataFrame(schema={aso_id: pl.Int64 for aso_id in aso_ids}).transpose(include_header=True, header_column_name='ASO_ID', column_names=[])

            if abs(actual_genes_submitted_count - total_genes_for_matrix) > 0.05 * total_genes_for_matrix: 
                 logging.warning(f"Number of genes submitted for processing ({actual_genes_submitted_count}) "
                                 f"differs from the initially provided total_genes_for_matrix ({total_genes_for_matrix}). "
                                 "Progress ETA might be inaccurate.")

            logging.info(f"Submitted {len(futures)} genes for processing. Waiting for completion...")

            for future in concurrent.futures.as_completed(futures):
                try:
                    progress_tracker.update() 
                    gene_id_processed, aso_counts_for_gene = future.result()
                    results_per_gene[gene_id_processed] = aso_counts_for_gene
                except Exception as e:
                    logging.error(f"Error processing a gene future: {e}")
        
        if self.verbose:
            logging.info(f"Finished parallel gene processing. Successfully obtained results for {len(results_per_gene)} genes.")

        if not results_per_gene:
            logging.warning("No gene processing results obtained after parallel execution. Returning an empty matrix.")
            return pl.DataFrame(schema={aso_id: pl.Int64 for aso_id in aso_ids}).transpose(include_header=True, header_column_name='ASO_ID', column_names=[])

        data_for_df: Dict[str, List[Any]] = {'ASO_ID': aso_ids}
        all_processed_gene_ids = sorted(list(results_per_gene.keys()))

        for gene_id_col in all_processed_gene_ids:
            data_for_df[gene_id_col] = [results_per_gene[gene_id_col].get(aso_id, 0) for aso_id in aso_ids]
        
        df = pl.DataFrame(data_for_df)

        if self.verbose:
            logging.info(f"Successfully created ASO x Gene matrix with shape: {df.shape}")
        return df
