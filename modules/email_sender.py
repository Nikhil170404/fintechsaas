import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


class EmailSender:
    def __init__(self, host: str, port: int, username: str, password: str, sender_name: str):
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.sender_name = sender_name

    def send(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        attachment_path: Path | None = None,
        attachment_name: str | None = None,
    ):
        msg = MIMEMultipart("alternative" if html_body else "mixed")
        msg["From"] = f"{self.sender_name} <{self.username}>"
        msg["To"] = f"{to_name} <{to_email}>"
        msg["Subject"] = subject

        # Plain text (always included as fallback)
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # HTML version
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))
            # Switch to mixed so we can also attach the PDF
            mixed = MIMEMultipart("mixed")
            mixed["From"] = msg["From"]
            mixed["To"] = msg["To"]
            mixed["Subject"] = msg["Subject"]
            mixed.attach(msg)
            msg = mixed

        if attachment_path:
            fname = attachment_name or Path(attachment_path).name
            with open(attachment_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=fname)
            part["Content-Disposition"] = f'attachment; filename="{fname}"'
            msg.attach(part)

        ctx = ssl.create_default_context()
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, context=ctx) as srv:
                srv.login(self.username, self.password)
                srv.sendmail(self.username, to_email, msg.as_string())
        else:
            with smtplib.SMTP(self.host, self.port) as srv:
                srv.ehlo()
                srv.starttls(context=ctx)
                srv.login(self.username, self.password)
                srv.sendmail(self.username, to_email, msg.as_string())
