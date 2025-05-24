#!/bin/bash


#SBATCH --job-name=ASODesignPipeline   # Job name
#SBATCH --ntasks=1                # Number of tasks (processes)
#SBATCH --cpus-per-task=64          # Number of CPU cores per task
#SBATCH --mem=128G                   # Memory per node
#SBATCH --time=24:00:00            # Time limit (hh:mm:ss)
#SBATCH --partition=comp       # Partition to submit to
#SBATCH --account=root        # Your account name


# Change to the directory where your script is located
cd /home/ayat/Repositories/ASODesignPipeline/data/kmc

ml load kmc

source /home/ayat/.venv/ASODesignPipeline/bin/activate

# kmc -k16 -m100 -v -fm /home/ayat/Repositories/ASODesignPipeline/data/genome/GRCh38_113/Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz GRCh38_113_k16.res /home/ayat/Repositories/ASODesignPipeline/data/kmc

kmc_tools transform GRCh38_113_k16.res dump GRCh38_113_k16.dump