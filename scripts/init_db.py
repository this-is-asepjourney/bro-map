"""
Buat extension PostGIS dan tabel (sinkron). Jalankan dari root proyek:
  python scripts/init_db.py
Membutuhkan psycopg2-binary dan DATABASE_URL yang dapat diakses (lihat .env.example).
"""

import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))

from config import settings  # noqa: E402
from database import Base  # noqa: E402
from models.place import Place  # noqa: E402, F401
from models.region import Region  # noqa: E402, F401


def main() -> None:
    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            Base.metadata.create_all(conn)
    except OperationalError as e:
        hint = (
            "\n\nPetunjuk:\n"
            "  • Pastikan Postgres jalan dan DATABASE_URL di .env (root proyek atau folder backend/) benar.\n"
            "  • Stack bawaan: `docker compose up -d db` — Postgres di host: **localhost:5433** "
            "(user `geofinder`, password `password`, DB `geofinder`).\n"
            "  • Set `DATABASE_URL` di `.env` ke `...@localhost:5433/...` bila init_db/backend dijalankan dari mesin host.\n"
            "  • Jika Anda sengaja memakai Postgres lain di port 5432, sesuaikan user/password di `DATABASE_URL`.\n"
        )
        raise SystemExit(f"Gagal konek database: {e}{hint}") from e
    print("Database siap:", url.split("@")[-1])


if __name__ == "__main__":
    main()
