import os
import gzip
import logging
from typing import Optional, List, Tuple, Dict, Any, Union
from Bio import SeqIO
import gget
import urllib.request, urllib.parse
from .utils import GenomeUtils



class GenomeDownloader:
    """
    Downloads the genome files for the specified species.
    """
    def __init__(self, 
                 species: str, 
                 e_release: int, 
                 genome_dir: str, 
                 verbose: bool = False
                 ) -> None:
        """
        Initializes the GenomeDownloader.

        Args:
            - species: The species name. e.g., 'homo_sapiens' or 'mus_musculus'.
            - e_release: The Ensembl release version.
            - genome_dir: Path to the parent directory where the genome index files will be saved.
            - verbose: If True, print verbose output.  
        """
        self.species = species
        self.e_release = e_release
        self.genome_dir = genome_dir
        self.verbose = verbose
        os.makedirs(self.genome_dir, exist_ok=True)
        
    def _download_file(self, 
                       url: str, 
                       output_path: str, 
                       file_type: str
                       ) -> None:
        """
        Helper method to download a file if it doesn't exist.
        """
        if not os.path.exists(output_path):
            if self.verbose:
                logging.info(f"Downloading {file_type} file to '{output_path}'")
            try:
                urllib.request.urlretrieve(url, output_path)
            except Exception as e:
                logging.error(f"Error downloading {file_type} file: {e}")
                raise e
        elif self.verbose:
            logging.info(f"{file_type} file already exists at '{output_path}'")

    def download(self) -> Tuple[str, str, str, Optional[str]]:
        """
        Downloads the genome files for the specified species.
        
        Returns Paths to the GTF, cDNA, genome FASTA files, and an optional scaffold GTF path, respectively.
        """
        gtf_url, cdna_url, genome_url = tuple(
            gget.ref(self.species, 
                     which=["gtf", "cdna", "dna"], 
                     release=self.e_release, 
                     ftp=True, 
                     verbose=False)
        )

        gtf_name = os.path.basename(urllib.parse.urlparse(gtf_url).path)
        cdna_name = os.path.basename(urllib.parse.urlparse(cdna_url).path)
        genome_name = os.path.basename(urllib.parse.urlparse(genome_url).path)

                
        gtf_path = os.path.join(self.genome_dir, gtf_name)
        cdna_path = os.path.join(self.genome_dir, cdna_name)
        genome_path = os.path.join(self.genome_dir, genome_name)

        self._download_file(gtf_url, gtf_path, "GTF")
        self._download_file(cdna_url, cdna_path, "cDNA")
        self._download_file(genome_url, genome_path, "genome FASTA")

        scaffold_gtf_path = None
        if self.species == 'homo_sapiens':     
            scaffold_gtf_url = gtf_url.replace('.gtf.gz', '.chr_patch_hapl_scaff.gtf.gz')
            
            scaffold_gtf_name = os.path.basename(urllib.parse.urlparse(scaffold_gtf_url).path)
            scaffold_gtf_path = os.path.join(self.genome_dir, scaffold_gtf_name)
            self._download_file(scaffold_gtf_url, scaffold_gtf_path, "scaffold GTF")
                
                
        return gtf_path, cdna_path, genome_path, scaffold_gtf_path


class GenomeDataManager:
    """
    Manages downloading, processing, and providing paths to essential genome data files.
    """
    def __init__(self,
                 gene_id: str,
                 species: str,
                 e_release: int,
                 genome_assembly: int,
                 genome_dir: str,
                 data_dir: str,
                 tsl_list_to_keep: Optional[List[Optional[int]]] = None,
                 protein_coding_only: bool = True,
                 verbose: bool = False
                 ):
        """
        Initializes the GenomeDataManager.
        
        Args:
            gene_id: The ID of the target gene.
            species: The species name. e.g., 'homo_sapiens' or 'mus_musculus'.
            e_release: The Ensembl release version. 
            genome_assembly: The genome assembly version. e.g., 38 for GRCh38.
            genome_dir: The parent directory where the genome files will be saved.
            tsl_list_to_keep: list of transcript support levels to keep. e.g., [1, 2, None].
            verbose: If True, print verbose output.
        """
        self.gene_id = gene_id
        self.species = species
        self.e_release = e_release
        self.genome_assembly = genome_assembly
        self.genome_dir = genome_dir
        self.data_dir = data_dir
        self.tsl_list_to_keep = tsl_list_to_keep
        self.protein_coding_only = protein_coding_only
        self.verbose = verbose
        
        logging.info(f"Indexing genome for gene: {self.gene_id}" + 
                    (f", species: {self.species}" if self.verbose else "") +
                    (f", release: {self.e_release}" if self.verbose else "") +
                    (f", protein_coding_only: {self.protein_coding_only}" if self.protein_coding_only else ""))

        if self.tsl_list_to_keep and self.verbose:
            logging.info(f"TSL filtering is active. Levels to keep: {self.tsl_list_to_keep}")
        elif self.verbose:
            logging.info("TSL filtering is not active or all levels are included.")

        genome_downloader = GenomeDownloader(
            species=self.species,
            e_release=self.e_release,
            genome_dir=self.genome_dir,
            verbose=self.verbose
        )
        
        (self.raw_gtf_path, 
         self.raw_cdna_path, 
         self.raw_genome_path, 
         self.raw_scaffold_gtf_path) = genome_downloader.download()

        if self.species.lower() == "mus_musculus":
            self.species = "Mus_musculus"
            reference_prefix = "GRCm"
        elif self.species.lower() == "homo_sapiens":
            self.species = "Homo_sapiens"
            reference_prefix = "GRCh"
        else:
            raise ValueError(f"Species {self.species} not supported. Please use 'homo_sapiens' or 'mus_musculus'.")
        
        main_reference_name = f'{reference_prefix}{self.genome_assembly}'
        self.genome_file_prefix = f'{self.species}.{main_reference_name}'
        
        self.genome = GenomeUtils.Genome(
            reference_name=main_reference_name,
            e_release=str(self.e_release),
            gtf_path=self.raw_gtf_path,
            transcript_fasta_paths=self.raw_cdna_path,
            primary_assembly_path=self.raw_genome_path,
            tsl_to_keep=self.tsl_list_to_keep,
            biotype_to_keep=["protein_coding"] if self.protein_coding_only else None,
            verbose=self.verbose
        )
        
        self.genome.index()
        logging.info(f"Main genome ('{main_reference_name}') indexed. Found {len(self.genome.genes)} genes.")

        self.genome_scaffolds: Optional[GenomeUtils.Genome] = None
        if self.raw_scaffold_gtf_path:
            # Assuming scaffold reference name might be different or need a suffix
            scaffold_reference_name = f'{main_reference_name}_scaffolds' 
            self.genome_scaffolds = GenomeUtils.Genome(
                reference_name=scaffold_reference_name,
                gtf_path=self.raw_scaffold_gtf_path,
            )
            self.genome_scaffolds.index(overwrite=False)
            if self.verbose:
                logging.info(f"Scaffold genome ('{scaffold_reference_name}') indexed.")

        self.target_gene: GenomeUtils.Gene = self.genome.gene_by_id(self.gene_id)
        if not self.target_gene:
            # Try scaffolds if not in primary assembly, though typically genes are on primary
            if self.genome_scaffolds:
                logging.warning(f"Target gene {self.gene_id} not found in primary assembly, checking scaffolds...")
                self.target_gene = self.genome_scaffolds.gene_by_id(self.gene_id)
            if not self.target_gene: # Still not found
                raise ValueError(f"Target gene {self.gene_id} not found in the main or scaffold genome assemblies.")
        
        self.target_gene.pre_mrna_sequence = self.genome.extract_premrna_sequences_per_gene(self.target_gene.gene_id)
        
        logging.info(f"Target gene '{self.target_gene.gene_name if hasattr(self.target_gene, 'gene_name') else self.gene_id}' loaded.")

        self.processed_gtf_path: Optional[str] = None
        self.processed_cdna_path: Optional[str] = None
        
        self.processed_cdna_excluding_target_path: Optional[str] = None
        self.processed_gtf_excluding_target_path: Optional[str] = None
        
        self.genes_pre_mrna_fasta_excludint_target_path: Optional[str] = None
        
        # self.processed_cdna_target_path: Optional[str] = None
        # self.processed_gtf_target_path: Optional[str] = None
        
        self.processed_cdna_path, self.processed_gtf_path = self.genome.export_genome_data(output_dir=self.genome_dir)
        self.processed_cdna_excluding_target_path, self.processed_gtf_excluding_target_path = self.genome.export_genome_data(output_dir=self.data_dir, exclude_ids=[self.gene_id])
        # self.processed_cdna_target_path, self.processed_gtf_target_path = self.target_gene.export_gene_data(output_dir=self.genome_dir)
        self.genes_pre_mrna_fasta_excludint_target_path = self.genome.export_pre_mrna_sequences(output_dir=self.data_dir, exclude_genes=[self.gene_id])

        if self.verbose:
            logging.info("GenomeDataManager initialization complete.")



    # --- Getter methods ---
    def get_target_gene_object(self) -> GenomeUtils.Gene:
        return self.target_gene

    def get_main_genome_object(self) -> GenomeUtils.Genome:
        return self.genome

    def get_scaffold_genome_object(self) -> Optional[GenomeUtils.Genome]:
        return self.genome_scaffolds

    def get_processed_cdna_path(self) -> str:
        """Path to cDNA FASTA, potentially TSL-filtered."""
        return self.processed_cdna_path

    def get_processed_cdna_excluding_target_path(self) -> Optional[str]:
        """Path to cDNA FASTA excluding target gene's transcripts."""
        return self.processed_cdna_excluding_target_path

    def get_genes_pre_mrna_fasta_excludint_target_path(self) -> Optional[str]:
        """Path to pre-mRNA FASTA for all genes excluding the target."""
        return self.genes_pre_mrna_fasta_excludint_target_path
    
    def get_processed_gtf_path(self) -> Optional[str]:
        """Path to the processed GTF file generated by export_genome_data."""
        return self.processed_gtf_path

    def get_raw_download_paths(self) -> Dict[str, Optional[str]]:
        return {
            "gtf": self.raw_gtf_path,
            "cdna": self.raw_cdna_path,
            "genome": self.raw_genome_path,
            "scaffold_gtf": self.raw_scaffold_gtf_path
        }





