import io
import os
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

_DEFAULT_API = "http://127.0.0.1:8010/api"


def _normalize_api_base(url: str) -> str:
    u = url.strip().rstrip("/")
    if not u.endswith("/api"):
        u = f"{u}/api"
    return u


def _resolve_api_url() -> str:
    if os.environ.get("API_URL"):
        return _normalize_api_base(os.environ["API_URL"])
    root_env = Path(__file__).resolve().parent.parent / ".env"
    if root_env.is_file():
        for raw in root_env.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("#") or not line.startswith("API_URL="):
                continue
            v = line.split("=", 1)[1].strip().strip('"').strip("'")
            if v:
                return _normalize_api_base(v)
    return _DEFAULT_API


API_URL = _resolve_api_url()

st.set_page_config(page_title="Geo Finder", page_icon="🗺️", layout="wide")
st.title("🗺️ Geo Finder — Pencarian Bisnis Berdasarkan Lokasi")

with st.sidebar:
    st.header("Filter Pencarian")

    category_label = st.text_input(
        "Kategori",
        value="Bengkel",
        placeholder="contoh: Bengkel, Restoran, Salon, Apotek",
        help="Ketik kategori bisnis bebas (mis. Bengkel, Restoran, Kafe, Apotek, dll).",
    )
    keyword = st.text_input(
        "Kata Kunci",
        value="bengkel motor",
        placeholder="contoh: bengkel motor, restoran sunda",
        help="Kata kunci pencarian yang dikirim ke Google Maps.",
    )

    st.subheader("Lokasi")
    province = st.text_input("Provinsi", value="Jawa Tengah", placeholder="contoh: Jawa Tengah")
    regency = st.text_input("Kabupaten / Kota", value="Semarang", placeholder="contoh: Kota Semarang")
    district = st.text_input("Kecamatan", value="Semarang Tengah", placeholder="contoh: Semarang Tengah")

    max_results = st.slider("Maks. Hasil", 5, 50, 20)

    search_btn = st.button("🔍 Cari Sekarang", use_container_width=True)
    st.caption(f"Backend: `{API_URL}`")

if search_btn:
    if not category_label.strip():
        st.warning("Kategori tidak boleh kosong.")
        st.stop()
    if not keyword.strip():
        st.warning("Kata kunci tidak boleh kosong.")
        st.stop()

    with st.spinner("Mengambil data dari Google Maps..."):
        payload = {
            "category": category_label.strip(),
            "keyword": keyword.strip(),
            "province": province,
            "regency": regency,
            "district": district,
            "max_results": max_results,
        }
        try:
            resp = requests.post(f"{API_URL}/search", json=payload, timeout=120)
        except requests.RequestException as e:
            st.error(f"Koneksi ke API gagal: {e}")
            st.stop()

    if resp.status_code == 200:
        data = resp.json()
        results = data["results"]
        cached = data.get("cached", False)

        if cached:
            st.info("Hasil diambil dari cache database (query sama dalam batas TTL).")
        st.success(f"Ditemukan **{data['total']} tempat** untuk: `{data['query']}`")

        df = pd.DataFrame(results)
        display_cols = [c for c in ["name", "address", "phone", "email", "rating", "open_hours"] if c in df.columns]
        if display_cols:
            st.dataframe(df[display_cols], use_container_width=True, height=400)
        else:
            st.dataframe(df, use_container_width=True, height=400)

        col1, col2 = st.columns(2)
        with col1:
            csv_data = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇️ Export CSV (lokal)",
                csv_data,
                file_name="hasil_pencarian.csv",
                mime="text/csv",
            )
        with col2:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Hasil")
            st.download_button(
                "⬇️ Export Excel (lokal)",
                buf.getvalue(),
                file_name="hasil_pencarian.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    elif resp.status_code == 503:
        st.error(resp.json().get("detail", "GOOGLE_MAPS_API_KEY belum diatur."))
    else:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        st.error(f"Gagal mengambil data ({resp.status_code}): {detail}")
