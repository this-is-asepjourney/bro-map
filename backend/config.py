from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _BACKEND_DIR.parent

# Satu .env di root repo (jalankan dari mana saja) atau di backend/
_env_candidates = (_BACKEND_DIR / ".env", _PROJECT_ROOT / ".env")
_env_files = tuple(p for p in _env_candidates if p.is_file())
if not _env_files:
    _env_files = (".env",)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API key untuk Google Maps Platform (Places API - New).
    # Aktifkan "Places API (New)" pada Google Cloud Console.
    GOOGLE_MAPS_API_KEY: str = ""
    # Default untuk `docker compose up -d db` (map host 5433 → container 5432)
    DATABASE_URL: str = "postgresql+asyncpg://geofinder:password@localhost:5433/geofinder"
    MAX_RESULTS_LIMIT: int = 50
    CACHE_TTL_HOURS: int = 168  # 7 days


settings = Settings()
