#!/bin/bash

# Usage:
#   ./load_password_interactive.sh <ORACLE_SID> [<PDB_NAME>]
#   If PDB_NAME is supplied, -pdb will be used in the load_password step

set -euo pipefail

ORACLE_SID="$1"
PDB_NAME="${2:-}"
HOSTNAME=$(hostname -s)
KEYSTORE_BASE="/home/oracle/ansible/keystores"
KEYSTORE_DIR="${KEYSTORE_BASE}/${HOSTNAME}-${ORACLE_SID}"

mkdir -p "$KEYSTORE_DIR"
chmod 700 "$KEYSTORE_DIR"

CONFIG_FILE="${KEYSTORE_DIR}/autoupgrade_load.cfg"

cat > "$CONFIG_FILE" <<EOF
global.keystore=${KEYSTORE_DIR}
EOF

echo "Launching AutoUpgrade to load TDE password"
echo "SID        : $ORACLE_SID"
[ -n "$PDB_NAME" ] && echo "PDB        : $PDB_NAME"
echo "Keystore   : $KEYSTORE_DIR"
echo

if [ -n "$PDB_NAME" ]; then
  java -jar "$ORACLE_HOME/rdbms/admin/autoupgrade.jar" \
    -config "$CONFIG_FILE" -load_password -pdb "$PDB_NAME"
else
  java -jar "$ORACLE_HOME/rdbms/admin/autoupgrade.jar" \
    -config "$CONFIG_FILE" -load_password
fi
