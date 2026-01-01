### Example 1.
import os

def read_user_file(filename):
    base_path = "/var/www/uploads/"
    filepath = base_path + filename
    with open(filepath, 'r') as f:
        return f.read()
### Example 2.

from pathlib import Path
def download_file(user_input):
    download_dir = Path("/downloads")
    file_path = download_dir / user_input
    return file_path.read_bytes()

### Example 3.

import tarfile
import tempfile

def extract_tar_archive(filename):
    tar = tarfile.open(filename)
    tar.extractall(path=tempfile.mkdtemp())
    tar.close()
