"""
config.py
---------
Loads all environment variables for the application.
Supports both a file named '.env' and the legacy 'env' file in the project root.
"""

from __future__ import annotations

import os
from pathlib import Path


def _find_env_file() -> str | None:
    """Return path to the env file, preferring .env over env."""
    base = Path(__file__).parent
    for name in (".env", "env"):
        candidate = base / name
        if candidate.exists():
            return str(candidate)
    return None


def _load_env_file(path: str) -> None:
    """Minimal .env loader — no external dependency required."""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_env_path = _find_env_file()
if _env_path:
    _load_env_file(_env_path)


# ---------------------------------------------------------------------------
# Typed config objects (plain dataclasses — no external pydantic required)
# ---------------------------------------------------------------------------

class _SnowflakeConfig:
    def __init__(self) -> None:
        self.account   = os.environ["SNOWFLAKE_ACCOUNT"]
        self.user      = os.environ["SNOWFLAKE_USER"]
        self.password  = os.environ["SNOWFLAKE_PASSWORD"]
        self.warehouse = os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
        self.database  = os.environ.get("SNOWFLAKE_DATABASE", "FIPSAR_DW")
        self.schema    = os.environ.get("SNOWFLAKE_SCHEMA", "GOLD")
        self.role      = os.environ.get("SNOWFLAKE_ROLE", "SYSADMIN")


class _AppConfig:
    def __init__(self) -> None:
        self.openai_api_key      = os.environ["OPENAI_API_KEY"]
        self.openai_model        = os.environ.get("OPENAI_MODEL", "gpt-4o")
        self.agent_max_iterations = int(os.environ.get("AGENT_MAX_ITERATIONS", "10"))
        self.search_max_rows     = int(os.environ.get("SEARCH_MAX_ROWS", "50"))


class _EmailConfig:
    """SMTP email settings for the FREL Agent report emailer."""
    def __init__(self) -> None:
        self.smtp_host     = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
        self.smtp_port     = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
        self.smtp_user     = os.environ.get("EMAIL_SMTP_USER", "")
        self.smtp_password = os.environ.get("EMAIL_SMTP_PASSWORD", "")
        self.from_name     = os.environ.get("EMAIL_FROM_NAME", "FIPSAR Intelligence")
        self.from_address  = os.environ.get("EMAIL_FROM_ADDRESS", self.smtp_user)
        self.to_address    = os.environ.get("EMAIL_TO", "akileshvishnu.m@gmail.com")

    @property
    def is_configured(self) -> bool:
        return bool(self.smtp_user and self.smtp_password)


snowflake_config = _SnowflakeConfig()
app_config       = _AppConfig()
email_config     = _EmailConfig()
