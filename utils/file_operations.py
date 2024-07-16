import os
from ftplib import FTP

def download_scaffold(path, genome_assembly, ensembl_release):
    """ Download the specified human scaffold from ENSEMBL if it is not already present in
        current directory. In either case, return the filename. """
    filepath = path + f"/GRCh{genome_assembly}/ensembl{ensembl_release}/"
    filename = f"Homo_sapiens.GRCh{genome_assembly}.{ensembl_release}.chr_patch_hapl_scaff.gtf.gz"

    if not os.path.exists(filepath+filename):  # Don't re-download.
        ftp = FTP('ftp.ensembl.org')
        ftp.login()
        ftp.cwd(f'pub/release-{ensembl_release}/gtf/homo_sapiens')
        
        os.makedirs(filepath, exist_ok=True)

        with open(filepath + filename, 'wb') as fp:
            ftp.retrbinary("RETR " + filename, fp.write)
            print('# Downloaded', filename)
    else:
        print('# Using', filename)
    return filename
