import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Iterable


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
        attachments: Iterable[tuple[Path, str | None]] | None = None,
    ):
        attachment_items = list(attachments or [])
        if attachment_path:
            attachment_items.insert(0, (attachment_path, attachment_name))

        if html_body and attachment_items:
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

        for path, label in attachment_items:
            fname = label or Path(path).name
            with open(path, "rb") as f:
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
