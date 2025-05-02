#!/usr/bin/env python3
"""
Simple Email Sender - Sends an email with an attachment
"""

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication


def send_email_with_attachment(
        sender_email,
        receiver_email,
        subject,
        body,
        attachment_path,
        smtp_server='smtp.gmail.com',
        smtp_port=587
):
    """
    Send an email with an attachment

    Parameters:
    - sender_email: Email address of the sender
    - receiver_email: Email address of the receiver
    - subject: Subject of the email
    - body: Body text of the email
    - attachment_path: Path to the file to be attached
    - smtp_server: SMTP server address
    - smtp_port: SMTP server port
    """
    # Create a multipart message
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject

    # Add body to email
    message.attach(MIMEText(body, "plain"))

    # Attach the file
    with open(attachment_path, "rb") as file:
        # Get the filename from the path
        filename = os.path.basename(attachment_path)
        attachment = MIMEApplication(file.read(), Name=filename)
        attachment["Content-Disposition"] = f'attachment; filename="{filename}"'
        message.attach(attachment)

    # Connect to the SMTP server
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()  # Secure the connection

        # If you need authentication, uncomment these lines and add your password
        # password = "your_password"  # Or get from environment variable
        # server.login(sender_email, password)

        # Send email
        server.sendmail(sender_email, receiver_email, message.as_string())
        print("Email sent successfully!")


# Example usage
if __name__ == "__main__":
    sender = "your_email@example.com"
    receiver = "recipient@example.com"
    subject = "Email with attachment"
    body = "Please find the attached file."
    attachment = "/path/to/your/file.pdf"  # Change this to your file path

    # For Gmail, you might need to enable "Less secure app access"
    # or use an App Password if you have 2FA enabled
    send_email_with_attachment(sender, receiver, subject, body, attachment)

# Example with authentication using environment variables:
"""
if __name__ == "__main__":
    sender = "your_email@example.com"
    receiver = "recipient@example.com"
    subject = "Email with attachment"
    body = "Please find the attached file."
    attachment = "/path/to/your/file.pdf"  # Change this to your file path

    # Using environment variables for secure password handling
    import os

    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login(sender, os.environ.get('EMAIL_PASSWORD'))

        message = MIMEMultipart()
        message["From"] = sender
        message["To"] = receiver
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain"))

        with open(attachment, "rb") as file:
            filename = os.path.basename(attachment)
            attachment = MIMEApplication(file.read(), Name=filename)
            attachment["Content-Disposition"] = f'attachment; filename="{filename}"'
            message.attach(attachment)

        server.sendmail(sender, receiver, message.as_string())
        print("Email sent successfully!")
"""