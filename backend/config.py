import os
from dataclasses import dataclass
from functools import lru_cache
from typing import List

from dotenv import load_dotenv


load_dotenv()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    env: str = os.getenv("ENV", "development")
    cors_origins: str = os.getenv("CORS_ORIGINS", "")

    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_exp_hours: int = _int_env("JWT_EXP_HOURS", 24)
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")

    db_path: str = os.getenv("DB_PATH", "./hiveos.db")

    influx_url: str = os.getenv("INFLUX_URL", "http://localhost:8086")
    influx_token: str = os.getenv("INFLUX_TOKEN", "")
    influx_org: str = os.getenv("INFLUX_ORG", "")
    influx_bucket: str = os.getenv("INFLUX_BUCKET", "beehive")
    ingest_api_key: str = os.getenv("INGEST_API_KEY", "")

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    grafana_admin_user: str = os.getenv("GRAFANA_ADMIN_USER", "admin")
    grafana_admin_password: str = os.getenv("GRAFANA_ADMIN_PASSWORD", "change-me")

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    @property
    def allowed_origins(self) -> List[str]:
        raw = self.cors_origins.strip()
        if not raw:
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    def validate_runtime(self) -> None:
        if self.is_production:
            missing = []
            if not self.jwt_secret:
                missing.append("JWT_SECRET")
            if not self.admin_password:
                missing.append("ADMIN_PASSWORD")
            if not self.ingest_api_key:
                missing.append("INGEST_API_KEY")
            if missing:
                raise RuntimeError(f"Missing required production settings: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
