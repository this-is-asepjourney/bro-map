# 🗺️ Geo Finder — Project Blueprint

## Overview

Sistem pencarian bisnis berbasis lokasi (kategori bebas: bengkel, restoran, salon, apotek, dll.) menggunakan **Google Maps Platform — Places API (New)** langsung, dengan filter geofence wilayah Indonesia (Provinsi → Kabupaten → Kecamatan).

---

## Stack

| Layer | Tool | Keterangan |
|---|---|---|
| Frontend | Streamlit | UI form pencarian + tabel hasil |
| Backend | FastAPI | REST API, orchestrator scraping |
| Maps Data | Google Maps Platform — Places API (New) | Text Search + detail (phone, website, hours) dalam satu panggilan via FieldMask |
| Database | PostgreSQL + PostGIS | Simpan hasil + query geospasial |
| Geofence | GeoJSON OpenStreetMap | Batas wilayah Indonesia |
| Export | Pandas | CSV / Excel output |

---

## Struktur Folder

```
geo-finder/
│
├── backend/
│   ├── main.py                  # FastAPI entry point
│   ├── routers/
│   │   ├── search.py            # endpoint POST /search
│   │   ├── export.py            # endpoint GET /export
│   │   └── regions.py           # endpoint GET /regions (provinsi/kab/kec)
│   ├── services/
│   │   ├── scraper.py           # Google Places API (New) integration
│   │   ├── geofence.py          # PostGIS filter wilayah
│   │   └── exporter.py          # Pandas CSV/Excel
│   ├── models/
│   │   ├── place.py             # SQLAlchemy model Place
│   │   └── region.py            # SQLAlchemy model Region
│   ├── schemas/
│   │   ├── search.py            # Pydantic schema request/response
│   │   └── place.py             # Pydantic schema Place
│   ├── database.py              # DB connection (SQLAlchemy + asyncpg)
│   └── config.py                # env vars (GOOGLE_MAPS_API_KEY, DB_URL, dll)
│
├── frontend/
│   └── app.py                   # Streamlit UI
│
├── data/
│   └── geojson/
│       ├── indonesia_provinces.geojson
│       ├── indonesia_regencies.geojson
│       └── indonesia_districts.geojson
│
├── scripts/
│   ├── import_geojson.py        # Load GeoJSON ke PostGIS
│   └── init_db.py               # Buat tabel database
│
├── .env                         # API keys & config
├── requirements.txt
├── docker-compose.yml
└── README.md
```

---

## Database Schema

### Tabel: `places`

```sql
CREATE TABLE places (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    category    VARCHAR(100),
    address     TEXT,
    phone       VARCHAR(50),
    email       VARCHAR(150),
    rating      NUMERIC(2,1),
    total_reviews INT,
    open_hours  JSONB,           -- { "senin": "08:00-17:00", ... }
    website     TEXT,
    maps_url    TEXT,
    location    GEOGRAPHY(POINT, 4326),   -- PostGIS point
    province    VARCHAR(100),
    regency     VARCHAR(100),
    district    VARCHAR(100),
    scraped_at  TIMESTAMP DEFAULT NOW(),
    search_query VARCHAR(255)
);

CREATE INDEX idx_places_location ON places USING GIST(location);
CREATE INDEX idx_places_category ON places(category);
CREATE INDEX idx_places_province ON places(province);
```

### Tabel: `regions` (dari import GeoJSON)

```sql
CREATE TABLE regions (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(150),
    level       VARCHAR(20),      -- 'province' | 'regency' | 'district'
    parent_id   INT REFERENCES regions(id),
    boundary    GEOGRAPHY(MULTIPOLYGON, 4326)   -- PostGIS polygon
);

CREATE INDEX idx_regions_boundary ON regions USING GIST(boundary);
CREATE INDEX idx_regions_level ON regions(level);
```

---

## API Endpoints (FastAPI)

### `POST /api/search`

Request body:
```json
{
  "category": "bengkel",
  "keyword": "bengkel motor",
  "province": "Jawa Tengah",
  "regency": "Semarang",
  "district": "Semarang Tengah",
  "max_results": 20
}
```

Response:
```json
{
  "total": 15,
  "query": "bengkel motor Semarang Tengah Semarang Jawa Tengah",
  "results": [
    {
      "name": "Bengkel Jaya Motor",
      "address": "Jl. Pemuda No. 12, Semarang",
      "phone": "024-8765432",
      "email": null,
      "rating": 4.5,
      "open_hours": { "senin-sabtu": "08:00-17:00" },
      "maps_url": "https://maps.google.com/?...",
      "latitude": -6.9934,
      "longitude": 110.4203
    }
  ]
}
```

### `GET /api/regions?level=province`
### `GET /api/regions?level=regency&parent=Jawa Tengah`
### `GET /api/regions?level=district&parent=Semarang`
### `GET /api/export?format=csv&search_id=abc123`

---

## Alur Kerja (Flow)

```
User input (Streamlit)
    │
    ▼
POST /api/search (FastAPI)
    │
    ├─► Validasi input (Pydantic)
    │
    ├─► Bangun query string:
    │     "{keyword} {district} {regency} {province}"
    │
    ├─► Cek cache di DB (apakah query yang sama sudah ada?)
    │     ├─ Ada → langsung return dari DB
    │     └─ Tidak ada → lanjut ke Google Places API
    │
    ├─► Google Places API (New) — Text Search:
    │     POST https://places.googleapis.com/v1/places:searchText
    │     headers: X-Goog-Api-Key, X-Goog-FieldMask
    │     body:    {textQuery, languageCode=id, regionCode=ID, maxResultCount}
    │     → respons sudah berisi phone, website, hours, rating (via FieldMask)
    │     → pagination otomatis lewat `nextPageToken` (hingga ±60 hasil)
    │
    ├─► Filter PostGIS:
    │     → ST_Within(place.location, region.boundary)
    │     → pastikan result benar-benar dalam batas kecamatan
    │
    ├─► Simpan ke tabel places
    │
    └─► Return JSON ke Streamlit
            │
            ▼
    Tampilkan tabel hasil
    + Peta Leaflet (opsional)
    + Tombol Export CSV/Excel
```

---

## Kode Utama

### `backend/config.py`

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    GOOGLE_MAPS_API_KEY: str
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost/geofinder"
    MAX_RESULTS_LIMIT: int = 50
    CACHE_TTL_HOURS: int = 168

    class Config:
        env_file = ".env"

settings = Settings()
```

### `backend/services/scraper.py`

```python
import httpx
from backend.config import settings

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

_FIELDS = ",".join([
    "places.id", "places.displayName", "places.formattedAddress",
    "places.location", "places.rating", "places.userRatingCount",
    "places.googleMapsUri", "places.internationalPhoneNumber",
    "places.nationalPhoneNumber", "places.websiteUri",
    "places.regularOpeningHours", "places.types", "places.primaryType",
    "nextPageToken",
])

async def search_google_maps(keyword: str, max_results: int = 20) -> list[dict]:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": _FIELDS,
    }
    body = {
        "textQuery": keyword,
        "languageCode": "id",
        "regionCode": "ID",
        "maxResultCount": min(max_results, 20),
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(PLACES_TEXT_SEARCH_URL, headers=headers, json=body)
        resp.raise_for_status()
    return resp.json().get("places", [])
```

Catatan: Detail (phone, website, opening hours) sudah ikut di respons Text Search
karena diminta lewat **FieldMask**, sehingga tidak perlu panggilan terpisah ke
Place Details.

### `backend/services/geofence.py`

```python
from sqlalchemy import text
from backend.database import async_session

async def filter_by_boundary(
    places: list[dict],
    province: str,
    regency: str,
    district: str
) -> list[dict]:
    """Filter places yang benar-benar dalam batas wilayah via PostGIS."""
    async with async_session() as db:
        result = await db.execute(
            text("""
                SELECT ST_AsGeoJSON(boundary)::json as geom
                FROM regions
                WHERE level = 'district'
                  AND name ILIKE :district
                LIMIT 1
            """),
            {"district": district}
        )
        row = result.fetchone()
    if not row:
        return places   # jika geofence tidak ditemukan, return semua

    boundary_geom = row.geom

    # Filter manual via PostGIS function
    filtered = []
    for p in places:
        lat, lng = p.get("latitude"), p.get("longitude")
        if lat and lng:
            async with async_session() as db:
                res = await db.execute(
                    text("""
                        SELECT ST_Within(
                            ST_SetSRID(ST_MakePoint(:lng, :lat), 4326),
                            ST_GeomFromGeoJSON(:boundary)
                        ) as inside
                    """),
                    {"lat": lat, "lng": lng, "boundary": str(boundary_geom)}
                )
                if res.scalar():
                    filtered.append(p)
        else:
            filtered.append(p)
    return filtered
```

### `backend/services/exporter.py`

```python
import pandas as pd
import io

def to_csv(places: list[dict]) -> bytes:
    df = pd.DataFrame(places)
    columns = ["name", "category", "address", "phone", "email",
               "rating", "open_hours", "website", "maps_url",
               "province", "regency", "district"]
    df = df.reindex(columns=columns)
    return df.to_csv(index=False).encode("utf-8-sig")


def to_excel(places: list[dict]) -> bytes:
    df = pd.DataFrame(places)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Hasil Pencarian")
    return buf.getvalue()
```

### `backend/routers/search.py`

```python
from fastapi import APIRouter
from backend.schemas.search import SearchRequest, SearchResponse
from backend.services.scraper import search_google_maps
from backend.services.geofence import filter_by_boundary
from backend.services.exporter import to_csv, to_excel

router = APIRouter(prefix="/api")

@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    query = f"{req.keyword} {req.district} {req.regency} {req.province}"

    # 1. Cari di Google Places API (New) — detail sudah ikut via FieldMask
    raw_results = await search_google_maps(query, req.max_results)

    # 2. Mapping ke shape internal
    enriched = []
    for r in raw_results:
        enriched.append({
            "name": r.get("name"),
            "address": r.get("address"),
            "rating": r.get("rating"),
            "total_reviews": r.get("total_reviews"),
            "maps_url": r.get("maps_url"),
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "category": req.category,
            "province": req.province,
            "regency": req.regency,
            "district": req.district,
            "phone": r.get("phone"),
            "website": r.get("website"),
            "open_hours": r.get("open_hours"),
            "email": None,
        })

    # 3. Filter geofence
    filtered = await filter_by_boundary(
        enriched, req.province, req.regency, req.district
    )

    return {"total": len(filtered), "query": query, "results": filtered}
```

### `frontend/app.py`

```python
import streamlit as st
import requests
import pandas as pd

API_URL = "http://localhost:8000/api"

st.set_page_config(page_title="Geo Finder", page_icon="🗺️", layout="wide")
st.title("🗺️ Geo Finder — Pencarian Bisnis Berdasarkan Lokasi")

# --- Sidebar: Form Input ---
with st.sidebar:
    st.header("Filter Pencarian")

    category = st.text_input(
        "Kategori",
        value="Bengkel",
        placeholder="contoh: Bengkel, Restoran, Salon, Apotek",
    )
    keyword = st.text_input("Kata Kunci", value="bengkel motor")

    st.subheader("Lokasi")
    province = st.text_input("Provinsi", value="Jawa Tengah")
    regency = st.text_input("Kabupaten / Kota", value="Semarang")
    district = st.text_input("Kecamatan", value="Semarang Tengah")
    max_results = st.slider("Maks. Hasil", 5, 50, 20)

    search_btn = st.button("🔍 Cari Sekarang", use_container_width=True)

# --- Main: Hasil ---
if search_btn:
    with st.spinner("Mengambil data dari Google Maps..."):
        payload = {
            "category": category,
            "keyword": keyword,
            "province": province,
            "regency": regency,
            "district": district,
            "max_results": max_results,
        }
        resp = requests.post(f"{API_URL}/search", json=payload)

    if resp.status_code == 200:
        data = resp.json()
        results = data["results"]

        st.success(f"Ditemukan **{data['total']} tempat** untuk: `{data['query']}`")

        # Tabel hasil
        df = pd.DataFrame(results)
        display_cols = ["name", "address", "phone", "email", "rating", "open_hours"]
        st.dataframe(df[display_cols], use_container_width=True, height=400)

        # Export
        col1, col2 = st.columns(2)
        with col1:
            csv_data = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ Export CSV", csv_data,
                               file_name="hasil_pencarian.csv", mime="text/csv")
        with col2:
            import io
            buf = io.BytesIO()
            df.to_excel(buf, index=False)
            st.download_button("⬇️ Export Excel", buf.getvalue(),
                               file_name="hasil_pencarian.xlsx",
                               mime="application/vnd.ms-excel")
    else:
        st.error("Gagal mengambil data. Cek API dan GOOGLE_MAPS_API_KEY.")
```

---

## Environment Variables (`.env`)

```env
GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
DATABASE_URL=postgresql+asyncpg://geofinder:password@localhost:5433/geofinder
API_URL=http://127.0.0.1:8010/api
MAX_RESULTS_LIMIT=50
CACHE_TTL_HOURS=168
```

> Aktifkan **Places API (New)** pada Google Cloud Console dan batasi
> API key (HTTP referrer / IP) sebelum dipakai di produksi.

---

## Docker Compose

```yaml
version: "3.9"
services:
  db:
    image: postgis/postgis:15-3.3
    environment:
      POSTGRES_USER: geofinder
      POSTGRES_PASSWORD: password
      POSTGRES_DB: geofinder
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - db
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    build: ./frontend
    ports:
      - "8501:8501"
    command: streamlit run app.py --server.port 8501

volumes:
  pgdata:
```

---

## `requirements.txt`

```
# Backend
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy[asyncio]==2.0.30
asyncpg==0.29.0
pydantic-settings==2.2.1
httpx==0.27.0
geoalchemy2==0.15.1
pandas==2.2.2
openpyxl==3.1.2

# Frontend
streamlit==1.35.0
requests==2.32.2
pandas==2.2.2
openpyxl==3.1.2
```

---

## Urutan Development (Roadmap)

### Fase 1 — Fondasi (Minggu 1-2)
- [ ] Setup PostgreSQL + PostGIS via Docker
- [ ] Import GeoJSON wilayah Indonesia ke tabel `regions`
- [ ] Buat tabel `places`
- [ ] Setup FastAPI project structure

### Fase 2 — Core Maps Integration (Minggu 2-3)
- [ ] Integrasi Google Places API (New): Text Search + FieldMask (detail dalam satu call)
- [ ] Endpoint POST /api/search
- [ ] Unit test scraper

### Fase 3 — Geofence (Minggu 3)
- [ ] Query PostGIS ST_Within
- [ ] Endpoint GET /api/regions (cascade dropdown)
- [ ] Validasi koordinat vs boundary

### Fase 4 — Frontend (Minggu 4)
- [ ] Form pencarian Streamlit
- [ ] Tabel hasil + pagination
- [ ] Export CSV / Excel
- [ ] Peta Leaflet (opsional via streamlit-folium)

### Fase 5 — Caching & Polish (Minggu 4-5)
- [ ] Cache hasil scraping di DB (avoid duplicate API call)
- [ ] Rate limiter Google Places API (hindari burst tagihan)
- [ ] Error handling & logging
- [ ] Deploy (Railway / VPS)

---

## Sumber Data GeoJSON Indonesia

- **OpenStreetMap Indonesia**: https://data.humdata.org/dataset/indonesia-administrative-boundary-polygons-levels-1-to-6
- **BPS (batas administrasi resmi)**: https://www.bps.go.id/
- **GitHub ina-geojson**: https://github.com/ans-4175/ina-geojson

---

## Catatan Penting

1. **Biaya Google Places API (New)**: Ditagih per request berdasarkan SKU (Text Search + field-field yang diminta). Gunakan **FieldMask seminimal mungkin** dan andalkan cache DB (default TTL 7 hari) untuk menekan biaya. Lihat https://developers.google.com/maps/billing-and-pricing/pricing#text-search
2. **Pagination**: Text Search (New) memberi maks. 20 hasil/halaman dan hingga 3 halaman via `nextPageToken` (±60 hasil total).
3. **Email tidak tersedia di Google Maps**: Untuk mendapatkan email bisnis, perlu scraping website bisnis yang muncul di hasil. Ini opsional dan lebih kompleks.
4. **Akurasi geofence**: Kualitas filter bergantung pada akurasi GeoJSON yang digunakan. Data OSM cukup baik untuk level kecamatan.
5. **Cache wajib**: Simpan hasil ke DB untuk menghindari pengeluaran API berulang untuk query yang sama.
6. **Restriksi API key**: Di production, batasi API key per HTTP referrer / IP dan hanya aktifkan "Places API (New)" — jangan commit key asli ke repo.
