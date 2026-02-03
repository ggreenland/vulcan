import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Development mode (enables /test/* endpoints)
    DEV_MODE: bool = os.getenv("DEV_MODE", "false").lower() == "true"

    # API key management (enables /api/keys/* endpoints and API key auth)
    ENABLE_API_KEYS: bool = os.getenv("ENABLE_API_KEYS", "false").lower() == "true"

    # Fireplace
    FIREPLACE_IP: str = os.getenv("FIREPLACE_IP", "192.168.0.22")
    FIREPLACE_PORT: int = int(os.getenv("FIREPLACE_PORT", "2000"))

    # Google OAuth
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")
    ALLOWED_EMAILS: list[str] = [
        e.strip() for e in os.getenv("ALLOWED_EMAILS", "").split(",") if e.strip()
    ]

    # App
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

    # Database
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "fireplace.db")


config = Config()
