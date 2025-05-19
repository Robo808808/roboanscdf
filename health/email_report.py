#!/usr/bin/env python3

import sys
import re

def extract_table_section(html, header_text):
    """Extract table rows for a given <h2> section title"""
    pattern = rf"<h2>{re.escape(header_text)}</h2>\s*<table>(.*?)</table>"
    match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else ""

def count_good_status(table_html, status_text):
    """Count how many rows have the desired good status"""
    rows = re.findall(r"<tr>(.*?)</tr>", table_html, re.DOTALL)
    data_rows = rows[1:]  # Skip header
    total = len(data_rows)
    good = sum(1 for row in data_rows if status_text in row)
    return total, good

def parse_summary(html_path):
    with open(html_path, 'r') as f:
        html = f.read()

    # Hostname
    host_match = re.search(r"<strong>Host:</strong>\s*(\S+)", html)
    hostname = host_match.group(1) if host_match else "UNKNOWN"

    # Extract database summary table only
    db_table = extract_table_section(html, "Database Summary")
    db_total, db_ok = count_good_status(db_table, "status-good\">OPEN")

    # Extract listener summary table only
    listener_table = extract_table_section(html, "Listener Summary")
    listener_total, listener_ok = count_good_status(listener_table, "status-good\">UP")

    summary = f"""Oracle Health Check Summary
Host: {hostname}
Databases: {db_ok} of {db_total} OK
Listeners: {listener_ok} of {listener_total} OK
"""
    print(summary.strip())

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: parse_report_summary.py <path_to_html_report>")
        sys.exit(1)

    parse_summary(sys.argv[1])
