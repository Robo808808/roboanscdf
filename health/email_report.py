#!/usr/bin/env python3

import sys
import re

def parse_summary(html_path):
    with open(html_path, 'r') as f:
        html = f.read()

    # Extract hostname
    host_match = re.search(r"<strong>Host:</strong>\s*(\S+)", html)
    hostname = host_match.group(1) if host_match else "UNKNOWN"

    # Count DB rows (skip header)
    db_rows = re.findall(r'<tr>\s*<td><a href="#db-', html)
    db_total = len(db_rows)
    db_ok = len(re.findall(r'<td class="status-good">OPEN</td>', html))

    # Count listener rows (skip header)
    listener_rows = re.findall(r'<tr>\s*<td><a href="#listener-', html)
    listener_total = len(listener_rows)
    listener_ok = len(re.findall(r'<td class="status-good">UP</td>', html))

    # Build plain text summary
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