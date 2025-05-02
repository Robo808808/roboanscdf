#!/usr/bin/env python3
"""
Email Sender Utility - Send emails with attachments

Usage:
    python email_sender.py --to recipient@example.com --subject "Email Subject"
                          --body "Email body text" --attachment /path/to/file.pdf
                          [--cc cc@example.com] [--bcc bcc@example.com]
"""

import argparse
import os
import smtplib
import sys
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
import getpass


def send_email(sender, recipients, subject, body, attachment_path=None,
               cc_recipients=None, bcc_recipients=None, smtp_server="smtp.gmail.com",
               smtp_port=587, use_tls=True, username=None, password=None):
    """
    Send an email with an optional attachment

    Args:
        sender (str): Sender's email address
        recipients (list): List of recipient email addresses
        subject (str): Email subject
        body (str): Email body text
        attachment_path (str, optional): Path to attachment file
        cc_recipients (list, optional): List of CC recipient email addresses
        bcc_recipients (list, optional): List of BCC recipient email addresses
        smtp_server (str): SMTP server address
        smtp_port (int): SMTP server port
        use_tls (bool): Whether to use TLS encryption

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    # Create message container
    message = MIMEMultipart()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject

    if cc_recipients:
        message["Cc"] = ", ".join(cc_recipients)

    if bcc_recipients:
        message["Bcc"] = ", ".join(bcc_recipients)

    # Add body to email
    message.attach(MIMEText(body, "plain"))

    # Add attachment if specified
    if attachment_path:
        try:
            attachment_path = Path(attachment_path)

            if not attachment_path.exists():
                print(f"Error: Attachment file not found: {attachment_path}")
                return False

            # Open file in binary mode
            with open(attachment_path, "rb") as attachment:
                # Add file as application/octet-stream
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())

            # Encode file in ASCII characters to send by email
            encoders.encode_base64(part)

            # Add header as key/value pair to attachment part
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={attachment_path.name}",
            )

            # Add attachment to message
            message.attach(part)

        except Exception as e:
            print(f"Error adding attachment: {e}")
            return False

    # Create SMTP session
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)

        if use_tls:
            server.starttls()  # Secure the connection

        # Authenticate only if username and password are provided
        if username and password:
            server.login(username, password)
        elif username and not password and sys.stdin.isatty():
            # If only username provided and we're in interactive mode, prompt for password
            input_password = getpass.getpass(
                f"Enter password for {username} (or set EMAIL_PASSWORD environment variable): ")
            if input_password:
                server.login(username, input_password)

        # Create a list of all recipient emails
        all_recipients = []
        all_recipients.extend(recipients)
        if cc_recipients:
            all_recipients.extend(cc_recipients)
        if bcc_recipients:
            all_recipients.extend(bcc_recipients)

        # Send email
        server.sendmail(sender, all_recipients, message.as_string())

        # Terminate the SMTP session
        server.quit()

        print("Email sent successfully!")
        return True

    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def main():
    """Parse command line arguments and send email"""
    parser = argparse.ArgumentParser(description="Send an email with attachment")

    parser.add_argument("--from", dest="sender",
                        help="Sender email address")
    parser.add_argument("--to", required=True,
                        help="Recipient email address(es), comma-separated")
    parser.add_argument("--cc",
                        help="CC recipient email address(es), comma-separated")
    parser.add_argument("--bcc",
                        help="BCC recipient email address(es), comma-separated")
    parser.add_argument("--subject", required=True,
                        help="Email subject")
    parser.add_argument("--body",
                        help="Email body text")
    parser.add_argument("--body-file",
                        help="File containing email body text")
    parser.add_argument("--attachment",
                        help="Path to attachment file")
    parser.add_argument("--smtp-server", default="smtp.gmail.com",
                        help="SMTP server address (default: smtp.gmail.com)")
    parser.add_argument("--smtp-port", type=int, default=587,
                        help="SMTP server port (default: 587)")
    parser.add_argument("--no-tls", action="store_true",
                        help="Disable TLS encryption")
    parser.add_argument("--username",
                        help="SMTP username (if different from sender email)")
    parser.add_argument("--password",
                        help="SMTP password (not recommended, use EMAIL_PASSWORD environment variable instead)")
    parser.add_argument("--no-auth", action="store_true",
                        help="Do not use SMTP authentication")

    args = parser.parse_args()

    # Get sender email
    sender = args.sender
    if not sender:
        sender = input("Enter sender email address: ")

    # Parse recipients
    recipients = [email.strip() for email in args.to.split(",")]

    # Parse CC recipients
    cc_recipients = None
    if args.cc:
        cc_recipients = [email.strip() for email in args.cc.split(",")]

    # Parse BCC recipients
    bcc_recipients = None
    if args.bcc:
        bcc_recipients = [email.strip() for email in args.bcc.split(",")]

    # Get email body
    body = args.body
    if args.body_file:
        try:
            with open(args.body_file, "r") as file:
                body = file.read()
        except Exception as e:
            print(f"Error reading body file: {e}")
            sys.exit(1)

    if not body:
        body = input("Enter email body text (end with Ctrl+D on Unix/Linux or Ctrl+Z on Windows):\n")

    # Determine authentication details
    username = args.username if args.username else sender
    password = args.password if args.password else os.environ.get('EMAIL_PASSWORD')

    # Send email
    success = send_email(
        sender=sender,
        recipients=recipients,
        subject=args.subject,
        body=body,
        attachment_path=args.attachment,
        cc_recipients=cc_recipients,
        bcc_recipients=bcc_recipients,
        smtp_server=args.smtp_server,
        smtp_port=args.smtp_port,
        use_tls=not args.no_tls,
        username=None if args.no_auth else username,
        password=None if args.no_auth else password
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()