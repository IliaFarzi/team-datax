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
FRONTEND_URL = os.getenv('FRONTEND_URL')

if not all([MAIL_HOST, MAIL_PORT, MAIL_USER, MAIL_PASSWORD, MAIL_FROM_NAME, MAIL_FROM_ADDRESS]):
    raise ValueError("Missing email configuration environment variables")


def send_email(to_address, subject, body):
    try:
        # Enforce TLS
        print(f"Attempting to connect to {MAIL_HOST}:{MAIL_PORT}")
        context = create_default_context()

        # Connect to the server
        with smtplib.SMTP_SSL(
             MAIL_HOST, MAIL_PORT, context=context
        ) as server:
            print("Connected to SMTP server")
            server.login(MAIL_USER, MAIL_PASSWORD)
            print("Logged in successfully")

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
    except smtplib.SMTPConnectError as e:
        raise Exception(f"SMTP connection failed: {str(e)} (Check MAIL_HOST and DNS)")
    except smtplib.SMTPAuthenticationError as e:
        raise Exception(f"SMTP authentication failed: {str(e)} (Check MAIL_USER and MAIL_PASSWORD)")
    except Exception as e:
        raise Exception(f"Failed to send email: {str(e)}")


def send_otp(email: str, otp: str):
    print(f"Sending OTP {otp} to {email}")

    subject = "Your OTP Code For DATAX"
    body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333; padding: 20px;">
            <h1 style="color: #2c3e50;">DATAX OTP Verification</h1>
            <p>Your one-time password (OTP) is: <strong style="font-size: 1.2em;">{otp}</strong></p>
            <p>This code is valid for 10 minutes.</p>
            <p style="margin-top: 20px;">
                <a href="{FRONTEND_URL}/checkEmail" style="background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Verify Now</a>
            </p>
            <p>If you did not request this, please ignore this email.</p>
            <p style="color: #7f8c8d;">Best regards,<br>DATAX Team</p>
        </body>
    </html>
    """

    send_email(email, subject, body)

    send_email(email, subject, body)