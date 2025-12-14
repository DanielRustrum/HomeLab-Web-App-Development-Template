from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env","backend/.env"), env_file_encoding="utf-8", extra="ignore")

    # App
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8080, alias="APP_PORT")
    app_env: str = Field(default="dev", alias="APP_ENV")  # dev|prod

    # Database (use DATABASE_URL or DB_* pieces)
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    db_host: str = Field(default="localhost", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_name: str = Field(default="homelab_app", alias="DB_NAME")
    db_user: str = Field(default="app", alias="DB_USER")
    db_password: str = Field(default="app_password", alias="DB_PASSWORD")

    @property
    def resolved_dsn(self) -> str:
        if self.database_url and self.database_url.strip():
            return self.database_url.strip()
        # psycopg uses RFC-1738 style URLs; "postgresql://" is fine.
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
