#api.app.email_sender.py
import smtplib
import os
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from ssl import create_default_context

load_dotenv = (".env")

MAIL_HOST = os.getenv("MAIL_HOST")
MAIL_PORT = os.getenv("MAIL_PORT")
MAIL_USER = os.getenv("MAIL_USER")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME")
MAIL_FROM_ADDRESS = os.getenv("MAIL_FROM_ADDRESS")



def send_email(to_address, subject, body):
    try:
        # Enforce TLS
        context = create_default_context()

        # Connect to the server
        with smtplib.SMTP_SSL(
             MAIL_HOST, MAIL_PORT, context=context
        ) as server:
            server.login(MAIL_USER, MAIL_PASSWORD)

            # Prepare the email
            msg = MIMEMultipart()
            msg["From"] = f"{MAIL_FROM_NAME} <{MAIL_FROM_ADDRESS}>"
            msg["To"] = to_address
            msg["Subject"] = subject
            # msg.add_header('x-liara-tag', 'test-tag')  # Add custom header
            msg.attach(MIMEText(body, "html"))

            # Send the email
            server.sendmail(MAIL_FROM_ADDRESS, to_address, msg.as_string())
            print(f"Email sent to {to_address} successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")


def send_otp(email: str, otp: str):
    print(f"Sending OTP {otp} to {email}")

    subject = "Your OTP Code For DATAX"
    body = f"""
        <h1>Your OTP Code</h1>
        <p>
            Your OTP code is: <strong>{otp}</strong>
        </p>
        """

    send_email(email, subject, body)