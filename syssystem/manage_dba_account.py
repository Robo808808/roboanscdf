#!/usr/bin/env python3

import sys
import json
import yaml
import shutil
import secrets
import string
import subprocess
from pathlib import Path
from datetime import datetime
from tempfile import NamedTemporaryFile

# === CONFIGURATION ===
VAULT_DIR = Path("group_vars/dba_accounts")
VAULT_FILE_LIST = VAULT_DIR / "dba_accounts_list.yml"
VAULT_PASS_FILE = Path("/home/oracle/.vault_pass")
VAULT_ID = "dba_vault"
VALID_ROLES = {"DBA", "MONITOR", "OPERATOR"}
PASSWORD_VAR = "dba_password"

# === FUNCTIONS ===

def generate_password(length=15):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def load_yaml_file(path):
    if not path.exists():
        return {'dba_accounts': []}
    with path.open("r") as f:
        return yaml.safe_load(f) or {'dba_accounts': []}

def write_yaml_safely(data, path):
    with NamedTemporaryFile("w", delete=False) as tmpf:
        yaml.dump(data, tmpf, default_flow_style=False)
        shutil.move(tmpf.name, path)

def backup_file(path):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(f".yml.bak.{timestamp}")
    shutil.copy2(path, backup)
    return str(backup)

def encrypt_password_to_vault(username, password):
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    vault_file = VAULT_DIR / f"{username}.yml"
    tmp_file = NamedTemporaryFile("w", delete=False)
    tmp_file.write(f"{PASSWORD_VAR}: \"{password}\"\n")
    tmp_file.close()

    cmd = [
        "ansible-vault", "encrypt", tmp_file.name,
        "--output", str(vault_file),
        "--vault-id", f"{VAULT_ID}@{VAULT_PASS_FILE}"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    Path(tmp_file.name).unlink()  # delete plain text
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return str(vault_file)

def json_output(status, message, password=None):
    output = {"status": status, "message": message}
    if password:
        output["password"] = password
    print(json.dumps(output))
    sys.exit(0 if status == "success" else 1)

# === MAIN ===

try:
    if len(sys.argv) < 3:
        json_output("error", "Usage: script.py [create|modify|delete] DBA_ID [ROLES]")

    action = sys.argv[1]
    dba_id = sys.argv[2]
    username = f"DBA_{dba_id}"
    roles = []

    if action in ("create", "modify") and len(sys.argv) >= 4:
        roles = [r.strip().upper() for r in sys.argv[3].split(",") if r.strip()]
        for role in roles:
            if role not in VALID_ROLES:
                json_output("error", f"Invalid role: {role}. Valid roles: {', '.join(VALID_ROLES)}")

    data = load_yaml_file(VAULT_FILE_LIST)
    accounts = data.get("dba_accounts", [])
    found = next((a for a in accounts if a["name"] == username), None)

    if action == "delete":
        if not found:
            json_output("error", f"User '{username}' not found")
        accounts.remove(found)
        backup_file(VAULT_FILE_LIST)
        write_yaml_safely({"dba_accounts": accounts}, VAULT_FILE_LIST)
        json_output("success", f"User '{username}' deleted")

    if action in ("create", "modify"):
        password = generate_password()
        encrypt_password_to_vault(username, password)

        if action == "create":
            if found:
                json_output("error", f"User '{username}' already exists")
            accounts.append({"name": username, "roles": roles})
            message = f"User '{username}' created"
        else:  # modify
            if not found:
                json_output("error", f"User '{username}' not found")
            found["roles"] = roles
            message = f"User '{username}' modified"

        backup_file(VAULT_FILE_LIST)
        write_yaml_safely({"dba_accounts": accounts}, VAULT_FILE_LIST)
        json_output("success", message, password)

    json_output("error", f"Unsupported action: {action}")

except Exception as e:
    json_output("error", f"Unexpected error: {str(e)}")
