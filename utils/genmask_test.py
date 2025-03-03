from Bio import SeqIO

def extract_sequences(fasta_file, bed_file):
    """
    Extracts sequences from a FASTA file based on coordinates in a BED-like file.

    Args:
        fasta_file (str): Path to the FASTA file.
        bed_file (str): Path to the BED-like file with coordinates.
    """

    # Create an index of the FASTA file for fast random access.
    record_dict = SeqIO.index(fasta_file, "fasta")

    with open(bed_file, 'r') as bed_in:
        for line in bed_in:
            line = line.strip()
            if not line:  # Skip empty lines
                continue

            fields = line.split('\t')
            if len(fields) < 4:
                print(f"Warning: Skipping line '{line}' - not enough fields.")
                continue

            chrom = fields[0]
            start = int(fields[1])
            end = int(fields[2])
            transcript_id = fields[3]  # Or whatever identifier you want

            try:
                record = record_dict[chrom]
                sequence = record.seq[start-1:end]  #FASTA is 1 based.  python is zero based.
                print(f">{transcript_id} {chrom}:{start}-{end}")
                print(sequence)
            except KeyError:
                print(f"Warning: Chromosome '{chrom}' not found in FASTA.")
            except IndexError:
                print(f"Warning: Coordinates {chrom}:{start}-{end} out of range.")


# Example Usage:
if __name__ == "__main__":
    fasta_file = "/home/ayat/Repositories/ASODesignPipeline/utils/GRCh38_masked.fa"  # Replace with your FASTA file
    bed_file = "/home/ayat/Repositories/ASODesignPipeline/KRAS.bed"  # Replace with your BED-like file
    extract_sequences(fasta_file, bed_file)