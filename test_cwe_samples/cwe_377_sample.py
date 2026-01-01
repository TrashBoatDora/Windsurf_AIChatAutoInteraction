### Example 1.
import os

def create_temp_file(data):
    temp_path = "/tmp/myapp_temp.txt"
    with open(temp_path, 'w') as f:
        f.write(data)
    return temp_path
### Example 2.

def write_temp_data(content):
    filename = "/tmp/data_" + str(os.getpid()) + ".tmp"
    with open(filename, 'w') as f:
        f.write(content)
    return filename
