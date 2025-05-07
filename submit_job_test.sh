#!/bin/bash


#SBATCH --job-name=ASODesignPipeline   # Job name
#SBATCH --ntasks=1                # Number of tasks (processes)
#SBATCH --cpus-per-task=64          # Number of CPU cores per task
#SBATCH --mem=128G                   # Memory per node
#SBATCH --time=24:00:00            # Time limit (hh:mm:ss)
#SBATCH --partition=comp       # Partition to submit to
#SBATCH --account=root        # Your account name


# Change to the directory where your script is located
cd /home/ayat/Repositories/ASODesignPipeline

ml load bowtie2

source /home/ayat/.venv/test/bin/activate

pip install -r requirements.txt

python main.py