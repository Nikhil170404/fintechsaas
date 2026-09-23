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

    # Fernet key for encrypting SMTP passwords at rest.
    # Auto-generated and persisted to data/.fernet_key on first run.
    @classmethod
    def _load_encryption_key(cls) -> str:
        key_file = os.path.join("data", ".fernet_key")
        env_key = os.environ.get("ENCRYPTION_KEY", "")
        if env_key and len(env_key) == 44:
            return env_key
        if os.path.exists(key_file):
            with open(key_file) as f:
                return f.read().strip()
        from cryptography.fernet import Fernet
        new_key = Fernet.generate_key().decode()
        os.makedirs("data", exist_ok=True)
        with open(key_file, "w") as f:
            f.write(new_key)
        return new_key

    ENCRYPTION_KEY: str = ""  # populated below


Config.ENCRYPTION_KEY = Config._load_encryption_key()
