#!/usr/bin/env python3

import sys
from bs4 import BeautifulSoup

def parse_summary(html_path):
    with open(html_path) as f:
        soup = BeautifulSoup(f, "html.parser")

    hostname = soup.find("strong", string="Host:").find_next().text
    db_rows = soup.select("h2:contains('Database Summary') + table tr")[1:]  # Skip header row
    listener_rows = soup.select("h2:contains('Listener Summary') + table tr")[1:]

    db_summary = [tr.find_all("td") for tr in db_rows]
    listener_summary = [tr.find_all("td") for tr in listener_rows]

    db_ok = sum(1 for row in db_summary if "status-good" in str(row[3]))
    db_total = len(db_summary)

    listeners_ok = sum(1 for row in listener_summary if "status-good" in str(row[1]))
    listeners_total = len(listener_summary)

    print(f"""
    Oracle Health Check Summary
    Host: {hostname}
    Databases: {db_ok} of {db_total} OK
    Listeners: {listeners_ok} of {listeners_total} OK
    """)

if __name__ == "__main__":
    parse_summary(sys.argv[1])
