#!/usr/bin/env python3
"""
Directory Comparison Tool

This script compares two directories and identifies:
1. Files that exist only in the first directory
2. Files that exist only in the second directory
3. Files that exist in both but have different content

Usage: python dir_compare.py <dir1> <dir2>
"""

import os
import sys
import hashlib
import filecmp
import argparse
from pathlib import Path


def calculate_file_hash(filepath):
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        return f"Error calculating hash: {e}"


def get_file_list(directory):
    """Get a list of all files in a directory and its subdirectories."""
    file_list = []
    try:
        for root, _, files in os.walk(directory):
            for file in files:
                full_path = os.path.join(root, file)
                # Store the path relative to the directory
                rel_path = os.path.relpath(full_path, directory)
                file_list.append(rel_path)
    except Exception as e:
        print(f"Error walking directory {directory}: {e}")
    return sorted(file_list)


def compare_files(file_path, dir1, dir2):
    """Compare two files and return their differences."""
    full_path1 = os.path.join(dir1, file_path)
    full_path2 = os.path.join(dir2, file_path)

    # First check if the files are binary identical
    if filecmp.cmp(full_path1, full_path2, shallow=False):
        return None

    # If they're not identical, get their hashes
    hash1 = calculate_file_hash(full_path1)
    hash2 = calculate_file_hash(full_path2)

    return {
        "path": file_path,
        "hash1": hash1,
        "hash2": hash2,
        "status": "DIFFERENT"
    }


def compare_directories(dir1, dir2):
    """Compare two directories and return the differences."""
    # Check if both directories exist
    if not os.path.isdir(dir1):
        print(f"Error: Directory '{dir1}' does not exist.")
        return None

    if not os.path.isdir(dir2):
        print(f"Error: Directory '{dir2}' does not exist.")
        return None

    # Get file lists
    files1 = get_file_list(dir1)
    files2 = get_file_list(dir2)

    # Files unique to dir1
    unique_to_dir1 = [f for f in files1 if f not in files2]

    # Files unique to dir2
    unique_to_dir2 = [f for f in files2 if f not in files1]

    # Files in both directories
    common_files = [f for f in files1 if f in files2]

    # Compare common files
    different_files = []
    for file in common_files:
        try:
            diff = compare_files(file, dir1, dir2)
            if diff:
                different_files.append(diff)
        except Exception as e:
            print(f"Error comparing file {file}: {e}")

    return {
        "dir1": dir1,
        "dir2": dir2,
        "unique_to_dir1": unique_to_dir1,
        "unique_to_dir2": unique_to_dir2,
        "different_files": different_files,
        "common_files": len(common_files),
        "total_files_dir1": len(files1),
        "total_files_dir2": len(files2)
    }


def print_results(results):
    """Print the comparison results in a readable format."""
    if not results:
        return

    print("\n" + "=" * 80)
    print(f"DIRECTORY COMPARISON RESULTS")
    print(f"Directory 1: {results['dir1']}")
    print(f"Directory 2: {results['dir2']}")
    print("=" * 80)

    print(f"\nSummary:")
    print(f"  Total files in Directory 1: {results['total_files_dir1']}")
    print(f"  Total files in Directory 2: {results['total_files_dir2']}")
    print(f"  Common files: {results['common_files']}")
    print(f"  Files only in Directory 1: {len(results['unique_to_dir1'])}")
    print(f"  Files only in Directory 2: {len(results['unique_to_dir2'])}")
    print(f"  Files with differences: {len(results['different_files'])}")

    # Print files unique to dir1
    if results['unique_to_dir1']:
        print("\n" + "-" * 80)
        print(f"FILES THAT EXIST ONLY IN DIRECTORY 1:")
        for file in results['unique_to_dir1']:
            print(f"  - {file} (does not exist in Directory 2)")

    # Print files unique to dir2
    if results['unique_to_dir2']:
        print("\n" + "-" * 80)
        print(f"FILES THAT EXIST ONLY IN DIRECTORY 2:")
        for file in results['unique_to_dir2']:
            print(f"  - {file} (does not exist in Directory 1)")

    # Print files with differences
    if results['different_files']:
        print("\n" + "-" * 80)
        print(f"FILES WITH DIFFERENCES:")
        for diff in results['different_files']:
            print(f"\n  File: {diff['path']}")
            print(f"  Hash in Directory 1: {diff['hash1']}")
            print(f"  Hash in Directory 2: {diff['hash2']}")


def main():
    parser = argparse.ArgumentParser(description='Compare two directories and find differences.')
    parser.add_argument('dir1', help='First directory to compare')
    parser.add_argument('dir2', help='Second directory to compare')
    args = parser.parse_args()

    dir1 = os.path.abspath(args.dir1)
    dir2 = os.path.abspath(args.dir2)

    print(f"Comparing directories:")
    print(f"Directory 1: {dir1}")
    print(f"Directory 2: {dir2}")
    print("Please wait, this may take some time depending on the size of the directories...")

    results = compare_directories(dir1, dir2)
    if results:
        print_results(results)


if __name__ == "__main__":
    main()