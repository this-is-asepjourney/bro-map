# 🚀 Deploy Geo Finder ke Coolify

Panduan langkah-demi-langkah untuk men-deploy project ini ke [Coolify](https://coolify.io) (self-hosted PaaS). Cocok untuk **Coolify v4** maupun versi terbaru.

> File deploy yang dipakai: `docker-compose.yml` di root repo.
> Override lokal (`docker-compose.override.yml`) **diabaikan** oleh Coolify — file itu hanya aktif saat Anda menjalankan `docker compose` di mesin lokal.

---

## Daftar Isi

1. [Prasyarat](#1-prasyarat)
2. [Persiapan Google Cloud (Places API)](#2-persiapan-google-cloud-places-api)
3. [Persiapan Repository Git](#3-persiapan-repository-git)
4. [Setup Resource di Coolify](#4-setup-resource-di-coolify)
5. [Set Environment Variables](#5-set-environment-variables)
6. [Atur Domain & HTTPS](#6-atur-domain--https)
7. [Deploy](#7-deploy)
8. [Verifikasi & Post-Deploy](#8-verifikasi--post-deploy)
9. [(Opsional) Impor GeoJSON untuk Geofence](#9-opsional-impor-geojson-untuk-geofence)
10. [Update / Rolling Deploy](#10-update--rolling-deploy)
11. [Backup Database](#11-backup-database)
12. [Troubleshooting](#12-troubleshooting)
13. [Checklist Final](#13-checklist-final)

---

## 1. Prasyarat

Sebelum mulai, pastikan Anda sudah punya:

- [ ] **Server Coolify aktif** (VPS dengan Coolify ter-install + akses panel UI)
- [ ] **Domain** yang DNS-nya sudah diarahkan ke IP server Coolify (`A record` → IP server)
- [ ] **Akun Google Cloud** dengan billing aktif (untuk Places API)
- [ ] **Git remote** (GitHub/GitLab/Gitea) tempat repo project ini di-push
- [ ] **Source Control terkoneksi** ke Coolify (GitHub App / Personal Access Token / Deploy Key)

---

## 2. Persiapan Google Cloud (Places API)

API key di file `.env` lokal **jangan** dipakai langsung di production. Buat key terpisah untuk Coolify.

### 2.1 Aktifkan Places API (New)

1. Buka https://console.cloud.google.com
2. Pilih atau buat **Project**.
3. **APIs & Services → Library** → cari **"Places API (New)"** → klik **Enable**.

   > Pastikan yang Anda enable adalah **"Places API (New)"**, BUKAN "Places API" (legacy). Project ini memakai endpoint baru `https://places.googleapis.com/v1/places:searchText`.

### 2.2 Buat API Key

1. **APIs & Services → Credentials → + Create Credentials → API key**
2. Catat key yang dihasilkan (mulai dengan `AIzaSy...`).

### 2.3 Restrict API Key (WAJIB sebelum production)

Klik nama key → **Edit API key**:

- **Application restrictions**:
  - Untuk panggilan **server-side** (project ini call dari container backend) → pilih **"IP addresses"** dan masukkan IP server Coolify Anda.
  - **JANGAN** pilih "HTTP referrers" karena yang memanggil API adalah Python backend, bukan browser.
- **API restrictions**:
  - Pilih **"Restrict key"** → centang **hanya "Places API (New)"**.

Tanpa restriction, API key Anda bisa disalahgunakan dan tagihan Google bisa membengkak.

### 2.4 Set Budget Alert (opsional tapi disarankan)

**Billing → Budgets & alerts → Create Budget** → set ambang misal $20/bulan dengan notifikasi email di 50%, 90%, 100%.

---

## 3. Persiapan Repository Git

### 3.1 Pastikan `.env` tidak ter-commit

```bash
git status
```

`.env` harus **tidak muncul** sebagai untracked atau staged. File `.gitignore` di repo sudah memblokirnya.

Jika `.env` sudah terlanjur masuk ke history:

```bash
git rm --cached .env
git commit -m "remove .env from tracking"
```

Lalu rotate API key Anda di Google Cloud (anggap key lama bocor).

### 3.2 Push repo ke remote

```bash
git add .
git commit -m "ready for coolify deploy"
git push -u origin main
```

Catat nama branch (`main` atau `master`).

---

## 4. Setup Resource di Coolify

### 4.1 Buat resource baru

1. Login ke panel Coolify.
2. Pilih **Project** (atau buat baru: `+ New → Project → "Geo Finder"`).
3. Di dalam project, pilih **Environment** (mis. `production`).
4. Klik **+ New Resource** → **Public Repository** atau **Private Repository** sesuai repo Anda.

### 4.2 Konfigurasi source

- **Repository URL**: `https://github.com/<user>/<repo>.git`
- **Branch**: `main` (atau sesuai branch Anda)
- **Build Pack**: pilih **"Docker Compose"**

### 4.3 Konfigurasi Docker Compose

Setelah memilih Docker Compose, Coolify akan minta path file compose:

- **Docker Compose Location**: `/docker-compose.yml`

  > ⚠️ **Penting**: default Coolify mencari `/docker-compose.yaml` (ekstensi `.yaml`). File di repo ini bernama `docker-compose.yml` (`.yml`). Ubah field ini menjadi `/docker-compose.yml`, atau Anda akan dapat error:
  >
  > `Docker Compose file not found at: /docker-compose.yaml`

- **Base Directory**: `/` (root repo)

Klik **Save** / **Continue**.

---

## 5. Set Environment Variables

Buka tab **Environment Variables** pada resource Anda. Isi variabel berikut:

| Variable | Value | Catatan |
|---|---|---|
| `GOOGLE_MAPS_API_KEY` | `AIzaSy...` | Key Coolify (yang sudah di-restrict per IP) |
| `POSTGRES_USER` | `geofinder` | bebas, tapi konsisten dengan DATABASE_URL |
| `POSTGRES_PASSWORD` | `<password kuat 24+ karakter>` | Generate via `openssl rand -base64 32` |
| `POSTGRES_DB` | `geofinder` | nama database |
| `DATABASE_URL` | `postgresql+asyncpg://geofinder:<password>@db:5432/geofinder` | ganti `<password>` dengan nilai `POSTGRES_PASSWORD` |
| `API_URL` | `http://backend:8000/api` | DNS internal — JANGAN pakai domain publik |
| `MAX_RESULTS_LIMIT` | `50` | maks. hasil per pencarian |
| `CACHE_TTL_HOURS` | `168` | 7 hari, hemat biaya API |

### Tips Coolify

- Centang **"Is Build Variable?"** = **false** untuk semua (variabel ini hanya dibutuhkan saat runtime, bukan saat build image).
- Untuk `GOOGLE_MAPS_API_KEY` dan `POSTGRES_PASSWORD` → centang **"Is Secret?"** = **true** supaya tersembunyi di log.

### Mengapa `API_URL=http://backend:8000/api`?

Frontend (Streamlit) memanggil API dari **server Python di dalam container**, bukan dari browser user. Jadi alamat yang dipakai adalah **DNS service Docker** (`backend`), bukan domain publik. Ini juga lebih cepat (tidak keluar-masuk reverse proxy).

---

## 6. Atur Domain & HTTPS

### 6.1 Frontend (UI publik)

1. Buka tab **Domains** / **General** pada service `frontend`.
2. Isi domain: `geofinder.example.com` (sesuaikan).
3. Pastikan port internal Coolify mengarah ke `8501` (sudah otomatis dari `expose: 8501` di compose).
4. Coolify akan otomatis:
   - Menambah label Traefik
   - Request sertifikat SSL via Let's Encrypt
   - Route HTTPS → container `frontend:8501`

### 6.2 Backend (TIDAK perlu domain publik)

Service `backend` **tidak perlu** domain. Frontend memanggilnya via DNS internal Docker.

Jika Anda mau backend bisa diakses publik (misal API untuk klien lain), tambahkan domain terpisah seperti `api.geofinder.example.com` di service `backend`.

### 6.3 DNS

Di registrar domain Anda, tambahkan record:

```
geofinder.example.com.   A   <IP server Coolify>
```

Tunggu propagasi (5–30 menit). Cek dengan:

```bash
dig +short geofinder.example.com
```

---

## 7. Deploy

### 7.1 Trigger pertama

Klik tombol **Deploy** di pojok kanan atas resource Coolify.

Anda akan melihat log build:

```
Cloning repository...
Building service db...
Building service backend...
Building service frontend...
Starting db... healthy
Starting backend... healthy
Starting frontend... healthy
✅ Deployment successful
```

Build pertama biasanya makan **3–7 menit** karena harus pull image PostGIS + install dependencies Python.

### 7.2 Auto-deploy berikutnya

Aktifkan **"Automatic Deployment"** di tab **Configuration** → setiap `git push` ke branch yang dipantau akan trigger redeploy.

---

## 8. Verifikasi & Post-Deploy

### 8.1 Cek service status

Di Coolify UI, semua 3 service harus `Running` + `Healthy`:

- `db` (postgis/postgis:15-3.3) — Healthy ✓
- `backend` (FastAPI) — Healthy ✓
- `frontend` (Streamlit) — Healthy ✓

### 8.2 Test endpoint

Dari laptop Anda:

```bash
# health check backend (lewat internal — gunakan Coolify Terminal)
curl https://geofinder.example.com   # → harus dapat halaman Streamlit
```

Atau gunakan tombol **"Open Application"** di Coolify yang langsung membuka domain.

### 8.3 Test pencarian end-to-end

1. Buka `https://geofinder.example.com` di browser.
2. Isi:
   - **Kategori**: `Bengkel`
   - **Kata Kunci**: `bengkel motor`
   - **Provinsi**: `Jawa Tengah`
   - **Kabupaten / Kota**: `Semarang`
   - **Kecamatan**: `Semarang Tengah`
3. Klik **Cari Sekarang**.
4. Hasil dari Google Maps harus muncul dalam ±5–15 detik.

Jika muncul tabel hasil → **deploy sukses**.

---

## 9. (Opsional) Impor GeoJSON untuk Geofence

Geofence membatasi hasil agar benar-benar dalam batas administratif yang dipilih. Kalau Anda **tidak** import GeoJSON, app tetap berjalan — filter wilayah akan di-skip.

### 9.1 Siapkan file GeoJSON

Letakkan file di repo Anda:

```
data/geojson/
  ├── indonesia_provinces.geojson
  ├── indonesia_regencies.geojson
  └── indonesia_districts.geojson
```

Sumber data: https://github.com/ans-4175/ina-geojson

Push ulang ke Git:

```bash
git add data/geojson/
git commit -m "add geojson data for geofencing"
git push
```

Coolify akan redeploy dan file akan tersedia di container backend (di-mount via `./data:/app/data:ro`).

### 9.2 Jalankan import script

Di Coolify, buka service `backend` → klik **Terminal** (atau **Execute Command**). Jalankan:

```bash
python /app/../scripts/import_geojson.py
```

> Catatan: script `import_geojson.py` ada di folder `scripts/` di root repo (bukan di `/app` container). Karena Docker build context backend hanya `./backend`, file ini **tidak otomatis ada di image**.
>
> Workaround tercepat: copy file masuk lewat Coolify Terminal:
>
> ```bash
> # dari host server Coolify (bukan dari container):
> docker cp scripts/import_geojson.py <backend-container-id>:/tmp/
> docker exec -it <backend-container-id> python /tmp/import_geojson.py
> ```

Setelah import sukses, tabel `regions` di Postgres terisi dan filter geofence aktif otomatis pada pencarian berikutnya.

---

## 10. Update / Rolling Deploy

Setelah setup awal, update kode tinggal push:

```bash
git add .
git commit -m "fix: tweak streamlit layout"
git push
```

Coolify akan:

1. Pull commit terbaru.
2. Build image baru (cache layer Docker akan dimanfaatkan, jadi cepat).
3. Start container baru, tunggu healthcheck pass.
4. Switch traffic dari container lama → baru (rolling update).
5. Hentikan container lama.

**Tidak ada downtime** untuk frontend selama healthcheck di-set dengan benar (sudah ada di `docker-compose.yml`).

---

## 11. Backup Database

Volume `pgdata` persist antar deploy, tapi **WAJIB** di-backup berkala.

### Opsi 1: Coolify Scheduled Backup (recommended)

1. Buka resource → service `db`.
2. Tab **Backups** → **Add S3 Backup** atau **Local Backup**.
3. Set cron `0 2 * * *` (setiap hari jam 02:00).

### Opsi 2: Manual via SSH

```bash
ssh user@server-coolify
docker ps   # cari container DB
docker exec <db-container> pg_dump -U geofinder geofinder > backup-$(date +%F).sql.gz
```

### Restore

```bash
cat backup-2026-05-13.sql | docker exec -i <db-container> psql -U geofinder -d geofinder
```

---

## 12. Troubleshooting

### `Docker Compose file not found at: /docker-compose.yaml`

**Solusi**: Di Coolify → Configuration → **Docker Compose Location** → ubah dari `/docker-compose.yaml` (default) menjadi `/docker-compose.yml`. Save → Redeploy.

### `password authentication failed for user "geofinder"`

Kredensial DB tidak sinkron antara service `db` dan `DATABASE_URL`. Cek di tab Environment Variables:

- `POSTGRES_PASSWORD` harus **persis sama** dengan password yang ada di `DATABASE_URL`.
- Jika baru saja diubah, volume `pgdata` masih menyimpan password lama. Solusi cepat: hapus volume (data hilang!) lalu redeploy.

```bash
docker volume rm <project>_pgdata
```

### Backend 503: `GOOGLE_MAPS_API_KEY belum diatur`

Variable belum di-load. Cek di Coolify → Environment Variables → pastikan `GOOGLE_MAPS_API_KEY` ada dan **tidak** centang "Is Build Variable" (harusnya runtime). Lalu **Redeploy**.

### Google Places: `REQUEST_DENIED` / `PERMISSION_DENIED`

Cek di Google Cloud:

1. Apakah **Places API (New)** sudah di-enable? (bukan yang legacy)
2. Apakah billing aktif?
3. IP server Coolify sudah ada di **Application restrictions**? Untuk test sementara, hapus restriction, lalu pasang lagi setelah konfirmasi jalan.

### Frontend 502 / WebSocket disconnect setiap beberapa detik

Streamlit perlu WebSocket. Traefik Coolify mendukung secara default, tapi cek:

1. Pastikan label Traefik terpasang (di Coolify, "Logs" → "Traefik labels detected").
2. Pastikan Anda tidak mengatur `Server.headers` atau middleware yang strip Upgrade header.

### Container `backend` keluar / restart-loop

Buka **Logs** service backend. Penyebab umum:

- DB belum siap → harusnya di-prevent oleh `depends_on: service_healthy`, tapi jika restart cepat, naikkan `start_period: 25s` → `60s`.
- Migration gagal (PostGIS extension tidak terinstall) → cek log apakah `CREATE EXTENSION IF NOT EXISTS postgis` muncul error. Gunakan image `postgis/postgis:15-3.3` (sudah pre-install PostGIS), bukan `postgres:15`.

### Streamlit error: `module 'altair' has no attribute 'themes'`

Konflik versi dependencies. Force-rebuild tanpa cache:

```
Coolify → Configuration → Force Rebuild → Deploy
```

---

## 13. Checklist Final

Sebelum klik Deploy, pastikan semua ✅:

- [ ] `.env` **tidak** ter-commit ke Git (`.gitignore` aktif)
- [ ] Repo sudah push ke remote, branch sesuai
- [ ] Google Cloud: **Places API (New)** enabled
- [ ] Google Cloud: billing aktif + budget alert
- [ ] API key Google sudah di-restrict per IP server Coolify
- [ ] Coolify: source repo terkoneksi
- [ ] Coolify: **Docker Compose Location** = `/docker-compose.yml`
- [ ] Coolify: semua 8 environment variables sudah diisi
- [ ] Coolify: `POSTGRES_PASSWORD` & `GOOGLE_MAPS_API_KEY` ditandai **Secret**
- [ ] Coolify: domain frontend sudah di-set + DNS A record sudah propagate
- [ ] Coolify: SSL Let's Encrypt status = active

Setelah semua ceklist hijau → **Deploy** → tunggu ±5 menit → akses domain Anda.

---

## Referensi

- [Coolify Documentation](https://coolify.io/docs)
- [Docker Compose specification](https://docs.docker.com/compose/compose-file/)
- [Google Places API (New)](https://developers.google.com/maps/documentation/places/web-service/text-search)
- [PostGIS Docker image](https://hub.docker.com/r/postgis/postgis)
- [Streamlit deployment behind reverse proxy](https://docs.streamlit.io/knowledge-base/deploy/remote-start)

Selamat deploying! 🎉
