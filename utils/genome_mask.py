#!/usr/bin/env python

import gget
from Bio import SeqIO
from Bio.Seq import Seq
import os
import urllib.request, urllib.parse
import gzip

def download_files():
    """
    Download the GRCh38 genome FASTA and GTF annotation files using gget.
    The files will be saved in the ./data directory.
    """
    data_dir = "/home/ayat/Repositories/ASODesignPipeline/data/genmap"
    genome_file = os.path.join(data_dir, "GRCh38.fa.gz")
    gtf_file = os.path.join(data_dir, "GRCh38.gtf")

    # Ensure the ./data directory exists
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    # Download GRCh38 FASTA URL.
    print("Retrieving GRCh38 genome FASTA URL...")
    genome_url = gget.ref("homo_sapiens", which="dna", release=113, ftp=True)[0]
    
    # Extract filename from URL
    parsed_url = urllib.parse.urlparse(genome_url)
    genome_file = os.path.join(data_dir, os.path.basename(parsed_url.path))
    
    # Download GRCh38 annotation in GTF format.
    print("Retrieving GRCh38 annotation GTF URL...")
    gtf_url = gget.ref("homo_sapiens", which="gtf", release=113, ftp=True)[0]
    
    # Extract filename from URL
    parsed_url = urllib.parse.urlparse(gtf_url)
    gtf_file = os.path.join(data_dir, os.path.basename(parsed_url.path))
    
    # Download GRCh38 FASTA
    print("Downloading GRCh38 genome FASTA...")
    # urllib.request.urlretrieve(genome_url, filename=genome_file)

    # Download GRCh38 GTF
    print("Downloading GRCh38 annotation GTF...")
    # urllib.request.urlretrieve(gtf_url, filename=gtf_file)
    

    return genome_file, gtf_file


def parse_gtf_for_introns(gtf_file):
    """
    Parse the GTF file to extract intron intervals for each transcript.
    Returns a dictionary keyed on chromosome (as in the FASTA headers) with a list
    of tuples (start, end) specifying the intron coordinates (1-indexed).
    Handles gzipped GTF files (.gtf.gz).
    """
    chr_exons = {}  # { transcript_id: {"chrom": chrom, "exons": [(start, end), ...]} }

    # Determine if the file is gzipped
    if gtf_file.endswith(".gz"):
        open_func = gzip.open
        mode = 'rt' #read as text
    else:
        open_func = open
        mode = 'r'

    with open_func(gtf_file, mode) as infile:
        for line in infile:
            if line.startswith("#"):
                continue
            fields = line.strip().split('\t')
            if len(fields) < 9 or fields[2] != "exon":
                continue

            chrom = fields[0]
            start = int(fields[3])
            end = int(fields[4])
            attributes = fields[8]
            

            if chrom not in chr_exons:
                chr_exons[chrom] = []
            chr_exons[chrom].append((start, end))
    
    intron_dict = {}
    # For every transcript with more than one exon, compute the intron intervals between consecutive exons.
    for chr, exons in chr_exons.items():
        if len(exons) < 2:
            continue
        exons_sorted = merge_intervals(exons)
        # Compute introns between each pair of consecutive exons.
        for i in range(len(exons_sorted) - 1):
            intron_start = exons_sorted[i][1] + 1
            intron_end = exons_sorted[i+1][0] - 1
            if intron_start <= intron_end:
                if chr not in intron_dict:
                    intron_dict[chr] = []
                intron_dict[chr].append((intron_start, intron_end))
    
    
    return intron_dict

def merge_intervals(intervals):
    """
    Merge overlapping or contiguous intervals.
    Both input and output intervals use 1-indexed coordinates.
    """
    if not intervals:
        return []
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_intervals[0]]
    for current in sorted_intervals[1:]:
        last = merged[-1]
        if current[0] <= last[1] + 1:
            merged[-1] = (last[0], max(last[1], current[1]))
        else:
            merged.append(current)
    return merged

def mask_introns(genome_file, intron_dict, output_file):
    """
    Mask the intronic regions in the genome FASTA file by replacing bases with 'N'.
    Handles gzipped FASTA files (.fa.gz).
    The intron_dict should map chromosome names to a list of (start, end) tuples (1-indexed).
    """

    # Determine if the genome file is gzipped and decompress if necessary
    if genome_file.endswith(".gz"):
        print("Decompressing gzipped genome file...")
        with gzip.open(genome_file, 'rt') as infile:
            records = list(SeqIO.parse(infile, "fasta"))
    else:
        records = list(SeqIO.parse(genome_file, "fasta"))

    masked_records = []
    for record in records:
        # Assume the record.id (or the first token) matches the chromosome naming in the GTF file.
        chrom = record.id.split()[0]
        seq_str = str(record.seq)
        seq_list = list(seq_str)  # Convert to list for mutability
        if chrom in intron_dict:
            for start, end in intron_dict[chrom]:
                # GTF is 1-indexed; convert to 0-indexed for Python lists.
                for i in range(start - 1, end):
                    if i < len(seq_list):
                        seq_list[i] = 'N'
        record.seq = Seq("".join(seq_list))
        masked_records.append(record)

    # Compress the output if the input was compressed
    if output_file.endswith(".gz"):
        print("Compressing masked genome file...")
        with gzip.open(output_file, "wt") as outfile:
            SeqIO.write(masked_records, outfile, "fasta")
    else:
        SeqIO.write(masked_records, output_file, "fasta")

    print(f"Masked genome saved to {output_file}")


def main():
    # Step 1: Download GRCh38 FASTA and GTF using gget.
    genome_file, gtf_file = download_files()
    
    # Step 2: Parse the GTF to extract intron intervals.
    print("Parsing the GTF file for intron coordinates...")
    intron_dict = parse_gtf_for_introns(gtf_file)
    
    # Step 3: Mask intron regions in the genome and write the masked FASTA.
    output_file = "/home/ayat/Repositories/ASODesignPipeline/data/genmap/GRCh38_masked.fa"
    print("Masking intron regions in the genome...")
    mask_introns(genome_file, intron_dict, output_file)
    
if __name__ == "__main__":
    main()
