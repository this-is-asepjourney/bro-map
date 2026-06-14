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


def _nonempty_mask(series: pd.Series) -> pd.Series:
    """True untuk sel yang punya teks nyata (bukan kosong / nan / 'None')."""
    if series is None or len(series) == 0:
        return pd.Series(dtype=bool)
    s = series.astype(object)
    out = pd.Series(False, index=series.index)
    ok = s.notna()
    if not ok.any():
        return out
    t = s[ok].astype(str).str.strip()
    out.loc[ok] = (t != "") & (t.str.lower() != "none") & (t.str.lower() != "nan")
    return out


def filter_results_df(
    df: pd.DataFrame,
    *,
    require_phone: bool = False,
    require_email: bool = False,
    require_website: bool = False,
) -> pd.DataFrame:
    """Buang baris yang tidak punya isi pada kolom yang dipilih (semua opsi AND)."""
    out = df.copy()
    if require_phone and "phone" in out.columns:
        out = out.loc[_nonempty_mask(out["phone"])].copy()
    if require_email and "email" in out.columns:
        out = out.loc[_nonempty_mask(out["email"])].copy()
    if require_website and "website" in out.columns:
        out = out.loc[_nonempty_mask(out["website"])].copy()
    return out


st.set_page_config(page_title="Geo Finder", page_icon="🗺️", layout="wide")
st.title("🗺️ Geo Finder — Pencarian Bisnis Berdasarkan Lokasi")

with st.sidebar:
    st.header("Filter Pencarian")

    category = st.text_input(
        "Kategori",
        value="",
        placeholder="mis. Bengkel, Restoran, Salon",
        help="Label kategori bebas teks (bukan daftar pilihan).",
    )
    keyword = st.text_input(
        "Kata kunci",
        value="restoran",
        placeholder="mis. restoran padang",
    )

    st.subheader("Lokasi")
    province = st.text_input("Provinsi", value="Jawa Tengah", placeholder="contoh: Jawa Tengah")
    regency = st.text_input("Kabupaten / Kota", value="Semarang", placeholder="contoh: Kota Semarang")
    district = st.text_input("Kecamatan", value="Semarang Tengah", placeholder="contoh: Semarang Tengah")

    max_results = st.slider("Maks. Hasil", 5, 50, 20)

    search_btn = st.button("🔍 Cari Sekarang", use_container_width=True)
    st.caption(f"Backend: `{API_URL}`")

    st.divider()
    st.subheader("Saring tampilan")
    st.caption("Sembunyikan baris yang **tidak punya** isi pada kolom berikut:")
    filter_require_phone = st.checkbox("Wajib ada nomor telepon", value=False, key="flt_phone")
    filter_require_email = st.checkbox("Wajib ada email", value=False, key="flt_email")
    filter_require_website = st.checkbox("Wajib ada situs web", value=False, key="flt_website")

if search_btn:
    if not keyword.strip():
        st.error("Kata kunci wajib diisi (minimal satu karakter).")
        st.stop()
    with st.spinner("Mengambil data dari Google Maps..."):
        payload = {
            "category": category.strip() or "Umum",
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
        st.session_state["results_df"] = pd.DataFrame(data["results"])
        st.session_state["search_meta"] = {
            "total": data["total"],
            "query": data["query"],
            "cached": data.get("cached", False),
        }
    elif resp.status_code == 503:
        st.session_state.pop("results_df", None)
        st.session_state.pop("search_meta", None)
        st.error(
            resp.json().get(
                "detail",
                "GOOGLE_MAPS_API_KEY belum diatur. Isi di .env dan aktifkan Places API (New).",
            )
        )
        st.stop()
    else:
        st.session_state.pop("results_df", None)
        st.session_state.pop("search_meta", None)
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        st.error(f"Gagal mengambil data ({resp.status_code}): {detail}")
        st.stop()

if "results_df" in st.session_state:
    df_src = st.session_state["results_df"]
    meta = st.session_state.get("search_meta") or {}

    df_view = filter_results_df(
        df_src,
        require_phone=filter_require_phone,
        require_email=filter_require_email,
        require_website=filter_require_website,
    )

    if meta.get("cached"):
        st.info("Hasil diambil dari cache database (query sama dalam batas TTL).")

    n_src, n_view = len(df_src), len(df_view)
    st.success(f"Pencarian: **{meta.get('total', n_src)}** tempat — `{meta.get('query', '')}`")
    if n_src == 0:
        st.warning("Tidak ada baris hasil untuk query ini.")
    elif n_view < n_src:
        st.caption(f"Setelah saringan: **{n_view}** baris ditampilkan (dari {n_src} total).")
    else:
        st.caption(f"Menampilkan **{n_view}** baris.")

    display_cols = [
        c for c in ["name", "address", "phone", "email", "website", "rating", "open_hours"] if c in df_view.columns
    ]
    if display_cols:
        st.dataframe(df_view[display_cols], use_container_width=True, height=400)
    else:
        st.dataframe(df_view, use_container_width=True, height=400)

    col1, col2 = st.columns(2)
    with col1:
        csv_data = df_view.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Export CSV (lokal)",
            csv_data,
            file_name="hasil_pencarian.csv",
            mime="text/csv",
        )
    with col2:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df_view.to_excel(writer, index=False, sheet_name="Hasil")
        st.download_button(
            "⬇️ Export Excel (lokal)",
            buf.getvalue(),
            file_name="hasil_pencarian.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
else:
    st.info("Atur filter di sidebar lalu klik **Cari Sekarang** untuk memuat hasil.")
