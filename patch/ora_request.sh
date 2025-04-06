#!/bin/bash

set -euo pipefail

EMAIL_TO="dba-team@example.com"
EMAIL_FROM="oracle-automation@example.com"

echo "Choose request type:"
select request_type in deinstall install patch patch-rollback; do
  if [[ -n "$request_type" ]]; then
    break
  else
    echo "Invalid choice. Please select again."
  fi
done

# === CONFIG SECTION ===
EMAIL_TO="dba-team@example.com"
EMAIL_FROM="oracle-automation@example.com"
TEAMS_WEBHOOK_URL="https://outlook.office.com/webhook/your-teams-webhook-url"

post_to_teams() {
  local title="$1"
  local message="$2"

  curl -s -H "Content-Type: application/json" \
    -d "{
      \"@type\": \"MessageCard\",
      \"@context\": \"http://schema.org/extensions\",
      \"summary\": \"$title\",
      \"themeColor\": \"0078D7\",
      \"title\": \"$title\",
      \"text\": \"$message\"
    }" \
    "$TEAMS_WEBHOOK_URL" > /dev/null
}

# Prompt for required inputs
hostname=""
oracle_sid=""
oracle_home=""
requested_mode=""
jobs_number=""

case "$request_type" in
  deinstall)
    read -rp "Enter hostname: " hostname
    read -rp "Enter ORACLE_HOME path: " oracle_home
    ;;
  install)
    read -rp "Enter ORACLE_SID: " oracle_sid
    hostname=$(hostname)
    ;;
  patch)
    read -rp "Enter ORACLE_SID: " oracle_sid
    read -rp "Enter ORACLE_HOME: " oracle_home
    echo "Select patch mode:"
    select requested_mode in analyze fixups deploy; do
      if [[ -n "$requested_mode" ]]; then break; fi
    done
    hostname=$(hostname)
    ;;
  patch-rollback)
    read -rp "Enter ORACLE_SID: " oracle_sid
    read -rp "Enter ORACLE_HOME: " oracle_home
    read -rp "Enter number of jobs to run: " jobs_number
    hostname=$(hostname)
    ;;
esac

# Timestamped logfile
timestamp=$(date +"%Y%m%d_%H%M%S")
logfile="${hostname}-${timestamp}.log"

# Playbook path and extra vars
case "$request_type" in
  deinstall)
    playbook="playbooks/deinstall_oracle_home.yml"
    extra_vars="-e oracle_home=${oracle_home}"
    ;;
  install)
    playbook="playbooks/install_oracle_software.yml"
    extra_vars="-e oracle_sid=${oracle_sid}"
    ;;
  patch)
    playbook="playbooks/patch_oracle_home.yml"
    extra_vars="-e oracle_sid=${oracle_sid} -e oracle_home=${oracle_home} -e requested_mode=${requested_mode}"
    ;;
  patch-rollback)
    playbook="playbooks/rollback_patch.yml"
    extra_vars="-e oracle_sid=${oracle_sid} -e oracle_home=${oracle_home} -e jobs=${jobs_number}"
    ;;
esac

# Compose message content
request_info=$(cat <<EOF
Request Type: $request_type
Hostname: $hostname
ORACLE_SID: $oracle_sid
ORACLE_HOME: $oracle_home
Patch Mode: $requested_mode
Jobs Number: $jobs_number
Log File: $logfile
EOF
)

# Send START email
echo "$request_info" | mailx -s "[STARTED] Oracle $request_type on $hostname" -r "$EMAIL_FROM" "$EMAIL_TO"

# Send START Teams message
post_to_teams "[STARTED] Oracle $request_type on $hostname" \
"Request Type: **$request_type**<br>Hostname: **$hostname**<br>SID: **$oracle_sid**<br>Log File: \`$logfile\`"

# Power Automate webhook URL
FLOW_URL="https://prod-123.westeurope.logic.azure.com:443/workflows/your-flow-id/..."

# Prepare card content
CARD_CONTENT=$(cat <<EOF
{
  "@type": "MessageCard",
  "@context": "http://schema.org/extensions",
  "summary": "Oracle Automation - $REQUEST_TYPE",
  "themeColor": "0078D7",
  "title": "Oracle Automation Job Started",
  "text": "Request: $REQUEST_TYPE\nSID: $ORACLE_SID\nHost: $HOSTNAME\nLog: $logfile",
  "attachments": [
    {
      "contentType": "application/vnd.microsoft.card.adaptive",
      "content": {
        "\$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.2",
        "body": [
          {
            "type": "TextBlock",
            "text": "🟢 Job Started\n📛 SID: $ORACLE_SID\n🧩 Type: $REQUEST_TYPE\n📁 Log: $logfile",
            "wrap": true
          }
        ]
      }
    }
  ]
}
EOF
)

# Background playbook runner script
cat <<EOF > "/tmp/run_ansible_${timestamp}.sh"
#!/bin/bash
ansible-playbook "$playbook" -i "$hostname," $extra_vars --vault-password-file ~/.vault_pass.txt > "$logfile" 2>&1

# Send COMPLETION email
echo "$request_info" | mailx -s "[COMPLETED] Oracle $request_type on $hostname" -a "$logfile" -r "$EMAIL_FROM" "$EMAIL_TO"

# Send Teams notification
curl -s -X POST -H "Content-Type: application/json" -d "$CARD_CONTENT" "$FLOW_URL"

EOF

chmod +x "/tmp/run_ansible_${timestamp}.sh"
nohup "/tmp/run_ansible_${timestamp}.sh" > /dev/null 2>&1 &

echo ""
echo "✅ Request submitted for type: $request_type"
echo "📄 Log file: $logfile"
echo "📧 Email notification sent to $EMAIL_TO"
