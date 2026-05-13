# Geo Finder (bro-map)

Pencarian bisnis berbasis lokasi: FastAPI + Streamlit + PostgreSQL/PostGIS + **Google Maps Platform (Places API New)**. Spesifikasi lengkap ada di [BLUEPRINT.md](./BLUEPRINT.md).

## Prasyarat

- Python 3.11+
- Docker (opsional) untuk PostGIS

## Setup cepat

1. Salin `.env.example` menjadi `.env` dan isi `GOOGLE_MAPS_API_KEY` (dari Google Cloud Console — aktifkan **Places API (New)**).

2. Jalankan database:

   ```bash
   docker compose up -d db
   ```

3. Inisialisasi skema:

   ```bash
   pip install -r requirements.txt
   python scripts/init_db.py
   ```

4. (Opsional) Impor GeoJSON wilayah ke `regions` — lihat `data/geojson/README.txt` dan `scripts/import_geojson.py`.

5. Backend (port **8010** di host supaya tidak bentrok dengan Django / app lain di **8000**):

   ```bash
   cd backend
   pip install -r requirements.txt
   uvicorn main:app --reload --host 127.0.0.1 --port 8010
   ```

6. Frontend:

   ```bash
   cd frontend
   pip install -r requirements.txt
   streamlit run app.py --server.port 8501
   ```

   Streamlit memakai `API_URL` dari variabel lingkungan, lalu dari file `.env` di root repo, lalu default `http://127.0.0.1:8010/api`. Opsional: tambahkan `API_URL=...` di `.env` jika backend Anda di port lain.

Atau satu perintah stack: `docker compose up --build` (set `.env` dengan `GOOGLE_MAPS_API_KEY`; `DATABASE_URL` di compose sudah mengarah ke service `db`). Backend FastAPI di host: **http://127.0.0.1:8010** (bukan 8000).

### Error `password authentication failed for user "geofinder"`

Biasanya **skrip/host menyambung ke Postgres yang salah**: di Windows sering sudah ada PostgreSQL di **port 5432**, sementara database proyek ini (Docker) dipetakan ke **port 5433** agar tidak bentrok.

- **Pakai DB dari `docker compose`:** jalankan `docker compose up -d db`, lalu di `.env` pastikan  
  `DATABASE_URL=...@localhost:5433/geofinder` (bukan `:5432`).
- **Tetap pakai Postgres lokal di 5432:** isi `DATABASE_URL` dengan user dan password yang benar untuk instalasi Anda (bukan `geofinder`/`password` kecuali Anda memang membuat user itu).

## API

- `POST /api/search` — body JSON sesuai blueprint
- `GET /api/regions?level=province|regency|district&parent=...`
- `GET /api/export?format=csv|xlsx&search_id=...` — `search_id` dikembalikan oleh `/api/search`

---

## Deploy ke Coolify

Project ini sudah disiapkan untuk Coolify (dan VPS biasa dengan Docker). Inti file deploy:

- `docker-compose.yml` — production-clean (tanpa `--reload`, tanpa port DB public, dengan healthcheck).
- `docker-compose.override.yml` — otomatis dimuat saat `docker compose up` lokal (expose port + hot-reload).
- `backend/Dockerfile` & `frontend/Dockerfile` — siap pakai, image kecil.
- `.env.example` — template variabel.
- `.gitignore` — mencegah `.env` & rahasia ter-commit.

### Langkah deploy

1. **Push repo** ke GitHub / GitLab. Pastikan `.env` **tidak** ikut (sudah ada di `.gitignore`).

2. **Google Cloud Console**:
   - Aktifkan **Places API (New)** di project Anda.
   - Buat / pilih API key, lalu set **Application restrictions** (HTTP referrer = domain Coolify Anda) dan **API restrictions** = hanya "Places API (New)".

3. **Di Coolify**:
   1. New Resource → **Docker Compose** → arahkan ke repository ini, branch utama.
   2. Pastikan Coolify membaca `docker-compose.yml` (file utama, bukan override).
   3. Buka tab **Environment Variables**, isi:

      | Variabel | Nilai |
      |---|---|
      | `GOOGLE_MAPS_API_KEY` | API key Google Anda |
      | `POSTGRES_USER` | `geofinder` (atau lainnya) |
      | `POSTGRES_PASSWORD` | password kuat (minimal 24 karakter) |
      | `POSTGRES_DB` | `geofinder` |
      | `DATABASE_URL` | `postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}` |
      | `API_URL` | `http://backend:8000/api` |
      | `MAX_RESULTS_LIMIT` | `50` |
      | `CACHE_TTL_HOURS` | `168` |

   4. Set **Domain** untuk service `frontend` (mis. `geofinder.example.com`). Coolify akan otomatis:
      - Pasang label Traefik
      - Terminate HTTPS via Let's Encrypt
      - Route `geofinder.example.com` → container `frontend:8501`

      Backend tidak perlu domain publik — frontend memanggilnya via DNS internal Docker (`http://backend:8000/api`).

   5. Klik **Deploy**. Healthcheck akan membuat Coolify menunggu DB siap → backend siap → frontend siap.

4. **(Opsional) Impor GeoJSON wilayah** agar geofence PostGIS aktif:
   - Upload file GeoJSON ke `data/geojson/` di repo (atau via Coolify Terminal `docker cp`).
   - Buka **Terminal** container `backend` di Coolify lalu jalankan:
     ```bash
     python /app/../scripts/import_geojson.py
     ```
     Jika geofence tidak diimpor, app tetap berjalan — filter wilayah dilewati saat region tidak ditemukan.

### Update / rolling deploy

Setiap `git push` ke branch yang dipantau Coolify akan trigger redeploy otomatis (kalau auto-deploy diaktifkan). Healthcheck mencegah Coolify menerima traffic sebelum service benar-benar siap.

### Backup database

Volume `pgdata` persist antar deploy. Backup berkala via Coolify "Scheduled Backup" atau cron host:

```bash
docker exec <db-container> pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup-$(date +%F).sql
```

### Troubleshooting

- **Frontend 502 / WebSocket disconnect**: pastikan Coolify proxy mengizinkan WebSocket (default di Traefik sudah on). Streamlit di-set `--server.enableCORS false --server.enableXsrfProtection false` di Dockerfile.
- **Backend 503 "GOOGLE_MAPS_API_KEY belum diatur"**: variabel belum di-load. Cek tab Environment Variables Coolify, lalu Redeploy.
- **DB connection refused**: tunggu healthcheck `db` selesai; backend punya `depends_on: db: service_healthy` sehingga harusnya menunggu otomatis.
- **Error Places API `REQUEST_DENIED`**: API key belum di-restrict dengan benar atau billing belum aktif di Google Cloud.
