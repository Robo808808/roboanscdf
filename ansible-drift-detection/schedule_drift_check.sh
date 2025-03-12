# schedule_drift_check.sh
#!/bin/bash

# This script schedules the Ansible playbook to run daily at midnight

ANSIBLE_PLAYBOOK_DIR="/path/to/ansible-drift-detection/playbooks"
LOG_DIR="/var/log/ansible/drift_reports"

mkdir -p "$LOG_DIR"