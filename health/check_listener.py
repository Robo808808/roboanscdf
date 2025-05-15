#!/usr/bin/env python3
import sys
import subprocess
import json
import os
import re


def parse_listener_ora(oracle_home):
    listener_file = os.path.join(oracle_home, "network", "admin", "listener.ora")
    listeners = []

    try:
        with open(listener_file, 'r') as f:
            content = f.read()

        # Extract listener names
        listener_sections = re.findall(r'(^\s*([A-Za-z0-9_]+)\s*=\s*\()', content, re.MULTILINE)

        for match in listener_sections:
            listeners.append(match[1])

        return listeners
    except Exception as e:
        return []


def check_listener(listener_name, oracle_home):
    os.environ["ORACLE_HOME"] = oracle_home
    os.environ["TNS_ADMIN"] = os.path.join(oracle_home, "network", "admin")

    result = {
        "listener_name": listener_name,
        "oracle_home": oracle_home,
        "status": "DOWN",
        "error": None,
        "services": []
    }

    try:
        # Run lsnrctl status to check listener status
        cmd = [os.path.join(oracle_home, "bin", "lsnrctl"), "status", listener_name]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            result["error"] = stderr if stderr else "Listener is down"
            return result

        result["status"] = "UP"

        # Parse services
        services_section = re.search(r'Services Summary.*?The command completed successfully', stdout, re.DOTALL)
        if services_section:
            services_text = services_section.group(0)
            service_lines = re.findall(r'"([^"]+)"', services_text)
            result["services"] = service_lines

        return result

    except Exception as e:
        result["error"] = str(e)
        return result


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: check_oracle_listener.py <LISTENER_NAME> <ORACLE_HOME>")
        sys.exit(1)

    listener_name = sys.argv[1]
    oracle_home = sys.argv[2]

    result = check_listener(listener_name, oracle_home)
    print(json.dumps(result))