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
        if html_body and attachment_path:
            # RFC 2387: multipart/mixed wraps a multipart/alternative inner part + attachment
            inner = MIMEMultipart("alternative")
            inner.attach(MIMEText(body, "plain", "utf-8"))
            inner.attach(MIMEText(html_body, "html", "utf-8"))
            msg = MIMEMultipart("mixed")
            msg.attach(inner)
        elif html_body:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
        else:
            msg = MIMEMultipart("mixed")
            msg.attach(MIMEText(body, "plain", "utf-8"))

        msg["From"] = f"{self.sender_name} <{self.username}>"
        msg["To"] = f"{to_name} <{to_email}>"
        msg["Subject"] = subject

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
