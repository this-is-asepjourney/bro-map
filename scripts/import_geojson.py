"""
Import GeoJSON administrasi Indonesia ke tabel `regions`.

Urutan disarankan: provinsi → kab/kota → kecamatan, agar parent_id terisi.

Contoh (sesuaikan path file):
  python scripts/import_geojson.py --file data/geojson/indonesia_provinces.geojson --level province
  python scripts/import_geojson.py --file data/geojson/indonesia_regencies.geojson --level regency \\
      --province-key NAME_1 --name-key NAME_2
  python scripts/import_geojson.py --file data/geojson/indonesia_districts.geojson --level district \\
      --province-key NAME_1 --regency-key NAME_2 --name-key NAME_3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from sqlalchemy import create_engine, text

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))

from config import settings  # noqa: E402


def _sync_url() -> str:
    return settings.DATABASE_URL


GEOM_EXPR = """
    ST_SetSRID(
        ST_Multi(ST_MakeValid(ST_GeomFromGeoJSON(:geom))),
        4326
    )::geography
"""


def _pick(props: dict, key: str | None, fallback_keys: list[str]) -> str | None:
    if key and props.get(key):
        return str(props[key]).strip()
    for k in fallback_keys:
        if props.get(k):
            return str(props[k]).strip()
    return None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True, help="Path ke file .geojson")
    p.add_argument("--level", required=True, choices=("province", "regency", "district"))
    p.add_argument("--name-key", default=None, help="Kunci nama di properties (contoh: NAME_3)")
    p.add_argument("--province-key", default="NAME_1", help="Kunci nama provinsi (untuk regency/district)")
    p.add_argument("--regency-key", default="NAME_2", help="Kunci nama kab/kota (untuk district)")
    args = p.parse_args()

    path = args.file if os.path.isabs(args.file) else os.path.join(ROOT, args.file)
    with open(path, encoding="utf-8") as f:
        gj = json.load(f)

    features = gj.get("features") or []
    engine = create_engine(_sync_url(), future=True)

    name_key = args.name_key
    if not name_key:
        name_key = {"province": "NAME_1", "regency": "NAME_2", "district": "NAME_3"}[args.level]

    with engine.begin() as conn:
        prov_by_name: dict[str, int] = {}
        reg_by_key: dict[tuple[str, str], int] = {}

        if args.level == "province":
            sql = text(
                f"""
                INSERT INTO regions (name, level, parent_id, boundary)
                VALUES (:name, 'province', NULL, {GEOM_EXPR})
                RETURNING id, name
                """
            )
            for feat in features:
                props = feat.get("properties") or {}
                name = _pick(props, name_key, ["NAME_1", "NM_PROP", "WADMPR", "name"])
                if not name:
                    continue
                geom = json.dumps(feat.get("geometry"))
                row = conn.execute(sql, {"name": name, "geom": geom}).fetchone()
                if row:
                    prov_by_name[name.lower()] = row[0]

        elif args.level == "regency":
            res = conn.execute(text("SELECT id, name FROM regions WHERE level = 'province'"))
            for rid, rname in res:
                if rname:
                    prov_by_name[str(rname).lower()] = rid

            sql = text(
                f"""
                INSERT INTO regions (name, level, parent_id, boundary)
                VALUES (:name, 'regency', :parent_id, {GEOM_EXPR})
                RETURNING id, name
                """
            )
            for feat in features:
                props = feat.get("properties") or {}
                pname = _pick(props, args.province_key, ["NAME_1"])
                rname = _pick(props, name_key, ["NAME_2", "NM_KAB", "name"])
                if not pname or not rname:
                    continue
                pid = prov_by_name.get(pname.lower())
                if pid is None:
                    continue
                geom = json.dumps(feat.get("geometry"))
                row = conn.execute(sql, {"name": rname, "parent_id": pid, "geom": geom}).fetchone()
                if row:
                    reg_by_key[(pname.lower(), rname.lower())] = row[0]

        else:
            res = conn.execute(
                text(
                    """
                    SELECT r.id, r.name, p.name AS pname
                    FROM regions r
                    JOIN regions p ON p.id = r.parent_id
                    WHERE r.level = 'regency'
                    """
                )
            )
            for rid, rname, pname in res:
                if rname and pname:
                    reg_by_key[(str(pname).lower(), str(rname).lower())] = rid

            sql = text(
                f"""
                INSERT INTO regions (name, level, parent_id, boundary)
                VALUES (:name, 'district', :parent_id, {GEOM_EXPR})
                """
            )
            for feat in features:
                props = feat.get("properties") or {}
                pname = _pick(props, args.province_key, ["NAME_1"])
                rname = _pick(props, args.regency_key, ["NAME_2"])
                dname = _pick(props, name_key, ["NAME_3", "NM_KEC", "name"])
                if not pname or not rname or not dname:
                    continue
                parent_id = reg_by_key.get((pname.lower(), rname.lower()))
                if parent_id is None:
                    continue
                geom = json.dumps(feat.get("geometry"))
                conn.execute(sql, {"name": dname, "parent_id": parent_id, "geom": geom})

    print("Selesai import", args.level, "dari", path, "- fitur:", len(features))


if __name__ == "__main__":
    main()
