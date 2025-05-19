#!/usr/bin/env python3

import sys
import re
import html
import subprocess

def extract_table_section(html_content, header_text):
    pattern = rf"<h2>{re.escape(header_text)}</h2>\s*<table>(.*?)</table>"
    match = re.search(pattern, html_content, re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else ""

def count_good_status(table_html, status_marker):
    rows = re.findall(r"<tr>(.*?)</tr>", table_html, re.DOTALL)
    data_rows = rows[1:]  # skip header row
    total = len(data_rows)
    good = sum(1 for row in data_rows if status_marker in row)
    return total, good

def get_command_output(cmd, fallback="UNKNOWN"):
    try:
        return subprocess.check_output(cmd, shell=True, text=True).strip()
    except Exception:
        return fallback

def get_host_metadata_from_file(meta_path):
    meta = {"hostname": "UNKNOWN", "os": "UNKNOWN", "kernel": "UNKNOWN", "uptime": "UNKNOWN"}
    try:
        with open(meta_path) as f:
            for line in f:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    meta[key] = html.escape(value)
    except Exception:
        pass
    return meta

def parse_summary(html_path):
    with open(html_path, 'r') as f:
        html_content = f.read()

    # Get host metadata
    meta = get_host_metadata_from_file(sys.argv[2])

    # Database Summary
    db_table = extract_table_section(html_content, "Database Summary")
    if db_table:
        db_total, db_ok = count_good_status(db_table, "status-good\">OPEN")
        db_summary = f"<p><strong>Databases:</strong> {db_ok} of {db_total} OK</p>"
    else:
        db_total = 0
        db_summary = "<p><strong>Databases:</strong> No databases found in report.</p>"

    # Listener Summary
    listener_table = extract_table_section(html_content, "Listener Summary")
    if listener_table:
        listener_total, listener_ok = count_good_status(listener_table, "status-good\">UP")
        listener_summary = f"<p><strong>Listeners:</strong> {listener_ok} of {listener_total} OK</p>"
    else:
        listener_total = 0
        listener_summary = "<p><strong>Listeners:</strong> No listeners found in report.</p>"

    # Compose full HTML body
    html_summary = f"""\
<html>
<body>
    <h2>Oracle Health Check Summary</h2>
    <p><strong>Host:</strong> {meta['hostname']}</p>
    <p><strong>OS:</strong> {meta['os']}</p>
    <p><strong>Kernel:</strong> {meta['kernel']}</p>
    <p><strong>Uptime:</strong> {meta['uptime']}</p>
    {db_summary}
    {listener_summary}
</body>
</html>
"""
    print(html_summary.strip())

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: parse_report_summary.py <path_to_html_report> <path_to_meta_file>")
        sys.exit(1)

    parse_summary(sys.argv[1])
