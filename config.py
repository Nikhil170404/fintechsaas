import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    COMPANY_NAME = os.environ.get("COMPANY_NAME", "FinTech Solutions Pvt Ltd")
    SENDER_NAME = os.environ.get("SENDER_NAME", "FinTech Solutions")
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASS = os.environ.get("SMTP_PASS", "")

    # System/transactional SMTP — used for password-reset emails, independent of
    # each tenant's own client-facing SMTP settings (which may not be configured yet).
    SYS_SMTP_HOST = os.environ.get("SYS_SMTP_HOST", "")
    SYS_SMTP_PORT = int(os.environ.get("SYS_SMTP_PORT", 587))
    SYS_SMTP_USER = os.environ.get("SYS_SMTP_USER", "")
    SYS_SMTP_PASS = os.environ.get("SYS_SMTP_PASS", "")
