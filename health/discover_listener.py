#!/usr/bin/env python3
import sys
import os
import re
import json


def discover_listeners(oracle_home):
    listener_file = os.path.join(oracle_home, "network", "admin", "listener.ora")
    listeners = []

    try:
        with open(listener_file, 'r') as f:
            content = f.read()

        # Extract listener names
        listener_sections = re.findall(r'(^\s*([A-Za-z0-9_]+)\s*=\s*\()', content, re.MULTILINE)

        for match in listener_sections:
            listeners.append(match[1])

        return {
            "oracle_home": oracle_home,
            "listeners": listeners,
            "listener_file": listener_file,
            "status": "SUCCESS"
        }
    except Exception as e:
        return {
            "oracle_home": oracle_home,
            "listeners": [],
            "status": "ERROR",
            "error": str(e)
        }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: discover_listeners.py <ORACLE_HOME>")
        sys.exit(1)

    oracle_home = sys.argv[1]
    result = discover_listeners(oracle_home)
    print(json.dumps(result))