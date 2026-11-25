import csv
import os
import hashlib

def get_file_hash(filepath):
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as afile:
        buf = afile.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = afile.read(65536)
    return hasher.hexdigest()

def extract_file(filepath):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Missing required source file: {filepath}")
    
    if os.path.getsize(filepath) == 0:
        raise ValueError(f"Source file is empty: {filepath}")
        
    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    return data, get_file_hash(filepath)
