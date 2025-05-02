#!/usr/bin/env python3
"""
Ansible Log Emailer - Sends an email with an Ansible log attachment and summarized content

Usage:
    python ansible_log_emailer.py --sender sender@example.com --receiver receiver@example.com
                              --subject "Ansible Run Summary" --attachment path/to/ansible.log
                              [--smtp-server mail.example.com]
"""

import argparse
import os
import re
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime


def parse_ansible_log(log_path):
    """
    Parse an Ansible log file and extract summary information

    Parameters:
    - log_path: Path to the Ansible log file

    Returns:
    - Dictionary with summary information
    """
    summary = {
        'total_tasks': 0,
        'ok': 0,
        'changed': 0,
        'unreachable': 0,
        'failed': 0,
        'skipped': 0,
        'rescued': 0,
        'ignored': 0,
        'start_time': None,
        'end_time': None,
        'duration': None,
        'hosts': set(),
        'failed_tasks': [],
        'changed_tasks': []
    }

    try:
        with open(log_path, 'r') as file:
            content = file.read()

            # Extract hosts
            host_matches = re.findall(r'\bOK: \[([^\]]+)\]', content)
            summary['hosts'].update(host_matches)

            # Extract play recap (if present)
            recap_match = re.search(r'PLAY RECAP \*+\s+(.*?)(?=\n\n|\Z)', content, re.DOTALL)
            if recap_match:
                recap = recap_match.group(1)

                # Extract host stats
                host_stats = re.findall(
                    r'([^\s:]+)\s+:\s+ok=(\d+)\s+changed=(\d+)\s+unreachable=(\d+)\s+failed=(\d+)\s+skipped=(\d+)(?:\s+rescued=(\d+)\s+ignored=(\d+))?',
                    recap)

                for match in host_stats:
                    host = match[0]
                    summary['hosts'].add(host)
                    summary['ok'] += int(match[1])
                    summary['changed'] += int(match[2])
                    summary['unreachable'] += int(match[3])
                    summary['failed'] += int(match[4])
                    summary['skipped'] += int(match[5])
                    if len(match) > 6:
                        summary['rescued'] += int(match[6] or 0)
                        summary['ignored'] += int(match[7] or 0)

            # Look for start time
            start_match = re.search(
                r'PLAY \[.*\] \*+\s+([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+)', content)
            if start_match:
                summary['start_time'] = start_match.group(1)

            # Look for end time (using the last timestamp)
            time_matches = re.findall(r'([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+)', content)
            if time_matches:
                summary['end_time'] = time_matches[-1]

            # Calculate duration if we have start and end times
            if summary['start_time'] and summary['end_time']:
                try:
                    start = datetime.strptime(summary['start_time'], '%Y-%m-%d %H:%M:%S.%f')
                    end = datetime.strptime(summary['end_time'], '%Y-%m-%d %H:%M:%S.%f')
                    summary['duration'] = str(end - start)
                except ValueError:
                    pass

            # Find failed tasks
            failed_matches = re.findall(r'fatal: \[([^\]]+)\]: FAILED!.*?=> (.*?)(?=\n\n|\Z)', content, re.DOTALL)
            for host, details in failed_matches:
                error_msg = re.sub(r'\s+', ' ', details).strip()
                summary['failed_tasks'].append(
                    {'host': host, 'error': error_msg[:100] + '...' if len(error_msg) > 100 else error_msg})

            # Find changed tasks
            changed_matches = re.findall(r'changed: \[([^\]]+)\].*?=> (.*?)(?=\n\n|\Z)', content, re.DOTALL)
            for host, details in changed_matches:
                task_info = re.sub(r'\s+', ' ', details).strip()
                summary['changed_tasks'].append(
                    {'host': host, 'details': task_info[:100] + '...' if len(task_info) > 100 else task_info})

            summary['total_tasks'] = summary['ok'] + summary['failed']  # Approximate

    except Exception as e:
        print(f"Error parsing log file: {e}")
        summary['error'] = str(e)

    return summary


def create_html_summary(summary):
    """
    Create an HTML summary of the Ansible run

    Parameters:
    - summary: Dictionary with summary information

    Returns:
    - HTML string with formatted summary
    """
    hosts_list = ', '.join(sorted(summary['hosts']))
    status_color = "green" if summary['failed'] == 0 and summary['unreachable'] == 0 else "red"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .summary {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; }}
            .status {{ color: {status_color}; font-weight: bold; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            .task-list {{ max-height: 300px; overflow-y: auto; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <h2>Ansible Run Summary</h2>
        <div class="summary">
            <p><strong>Status:</strong> <span class="status">{("SUCCESS" if summary['failed'] == 0 and summary['unreachable'] == 0 else "FAILED")}</span></p>
            <p><strong>Hosts:</strong> {hosts_list}</p>
            <p><strong>Duration:</strong> {summary['duration'] or 'Unknown'}</p>
    """

    # Add statistics table
    html += """
        <table>
            <tr>
                <th>Metric</th>
                <th>Count</th>
            </tr>
    """

    for stat in ['ok', 'changed', 'unreachable', 'failed', 'skipped', 'rescued', 'ignored']:
        html += f"""
            <tr>
                <td>{stat.capitalize()}</td>
                <td>{summary[stat]}</td>
            </tr>
        """

    html += """
        </table>
    </div>
    """

    # Add failed tasks if any
    if summary['failed_tasks']:
        html += """
        <h3>Failed Tasks</h3>
        <div class="task-list">
            <table>
                <tr>
                    <th>Host</th>
                    <th>Error</th>
                </tr>
        """

        for task in summary['failed_tasks']:
            html += f"""
                <tr>
                    <td>{task['host']}</td>
                    <td>{task['error']}</td>
                </tr>
            """

        html += """
            </table>
        </div>
        """

    # Add changed tasks if any
    if summary['changed_tasks']:
        html += """
        <h3>Changed Tasks</h3>
        <div class="task-list">
            <table>
                <tr>
                    <th>Host</th>
                    <th>Details</th>
                </tr>
        """

        for task in summary['changed_tasks'][:10]:  # Limit to 10 for brevity
            html += f"""
                <tr>
                    <td>{task['host']}</td>
                    <td>{task['details']}</td>
                </tr>
            """

        if len(summary['changed_tasks']) > 10:
            html += f"""
                <tr>
                    <td colspan="2">... and {len(summary['changed_tasks']) - 10} more changed tasks (see attachment for details)</td>
                </tr>
            """

        html += """
            </table>
        </div>
        """

    html += """
    <p>See the attached log file for complete details.</p>
    </body>
    </html>
    """

    return html


def send_email_with_attachment(sender_email, receiver_email, subject, log_path, smtp_server='localhost'):
    """
    Send an email with an Ansible log attachment and HTML summary

    Parameters:
    - sender_email: Email address of the sender
    - receiver_email: Email address of the receiver
    - subject: Subject of the email
    - log_path: Path to the Ansible log file
    - smtp_server: SMTP server address
    """
    # Parse the log file
    summary = parse_ansible_log(log_path)

    # Create HTML body
    html_body = create_html_summary(summary)

    # Create a multipart message
    message = MIMEMultipart('alternative')
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject

    # Create plain text version as fallback
    text_body = f"""
Ansible Run Summary

Status: {"SUCCESS" if summary['failed'] == 0 and summary['unreachable'] == 0 else "FAILED"}
Hosts: {', '.join(sorted(summary['hosts']))}
Duration: {summary['duration'] or 'Unknown'}

Statistics:
- OK: {summary['ok']}
- Changed: {summary['changed']}
- Unreachable: {summary['unreachable']}
- Failed: {summary['failed']}
- Skipped: {summary['skipped']}
- Rescued: {summary['rescued']}
- Ignored: {summary['ignored']}

See the attached log file for complete details.
"""

    # Attach parts
    message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    # Attach the log file
    try:
        with open(log_path, "rb") as file:
            # Get the filename from the path
            filename = os.path.basename(log_path)
            attachment = MIMEApplication(file.read(), Name=filename)
            attachment["Content-Disposition"] = f'attachment; filename="{filename}"'
            message.attach(attachment)
    except Exception as e:
        print(f"Error attaching log file: {e}")
        sys.exit(1)

    # Connect to the SMTP server and send
    try:
        with smtplib.SMTP(smtp_server) as server:
            server.sendmail(sender_email, receiver_email, message.as_string())
            print("Email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {e}")
        sys.exit(1)


def main():
    """Parse command line arguments and send email"""
    parser = argparse.ArgumentParser(description="Send an email with Ansible log attachment and summary")

    parser.add_argument("--sender", required=True, help="Sender email address")
    parser.add_argument("--receiver", required=True, help="Receiver email address")
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument("--attachment", required=True, help="Path to Ansible log file")
    parser.add_argument("--smtp-server", default="localhost", help="SMTP server address (default: localhost)")

    args = parser.parse_args()

    # Verify the log file exists
    if not os.path.isfile(args.attachment):
        print(f"Error: Log file not found: {args.attachment}")
        sys.exit(1)

    # Send the email
    send_email_with_attachment(
        sender_email=args.sender,
        receiver_email=args.receiver,
        subject=args.subject,
        log_path=args.attachment,
        smtp_server=args.smtp_server
    )


if __name__ == "__main__":
    main()