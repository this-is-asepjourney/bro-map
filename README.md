# Geo Finder (bro-map)

Pencarian bisnis berbasis lokasi: FastAPI + Streamlit + PostgreSQL/PostGIS + **Google Places API (New)**. Spesifikasi arsitektur ada di [BLUEPRINT.md](./BLUEPRINT.md) (beberapa contoh kode di sana masih menyebut SerpAPI; implementasi aktual memakai kunci Google Anda).

## Prasyarat

- Python 3.11+
- Docker (opsional) untuk PostGIS

## Setup cepat

1. Salin `.env.example` menjadi `.env`. Isi **`GOOGLE_MAPS_API_KEY`** dengan API key dari [Google Cloud Console](https://console.cloud.google.com/) dan aktifkan **Places API (New)** (Text Search + Place Details) untuk proyek tersebut. Nama variabel lama **`SERPAPI_KEY`** masih didukung sebagai alias. Jangan commit kunci ke git. Bila `.env` lama memakai `postgresql+asyncpg://`, ubah ke `postgresql+psycopg://`.

   **Kontak di hasil:** Google mengembalikan **nomor telepon** (internasional dan/atau nasional) serta **situs web**; **bukan email** di Places API. Secara default (`EMAIL_SCRAPE_FROM_WEBSITE=true`) backend mencoba mengekstrak **email dari HTML situs web** bisnis (best-effort, lebih lambat, bisa gagal). Set `EMAIL_SCRAPE_FROM_WEBSITE=false` untuk menonaktifkan.

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
   python -m uvicorn main:app --reload --host 127.0.0.1 --port 8010
   ```

6. Frontend:

   ```bash
   cd frontend
   pip install -r requirements.txt
   python -m streamlit run app.py --server.port 8501
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
