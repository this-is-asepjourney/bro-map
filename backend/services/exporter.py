import io

import pandas as pd


def _normalize_rows(places: list[dict]) -> list[dict]:
    rows = []
    for p in places:
        oh = p.get("open_hours")
        if isinstance(oh, (dict, list)):
            oh_str = str(oh)
        else:
            oh_str = oh
        rows.append(
            {
                "name": p.get("name"),
                "category": p.get("category"),
                "address": p.get("address"),
                "phone": p.get("phone"),
                "email": p.get("email"),
                "rating": p.get("rating"),
                "open_hours": oh_str,
                "website": p.get("website"),
                "maps_url": p.get("maps_url"),
                "province": p.get("province"),
                "regency": p.get("regency"),
                "district": p.get("district"),
                "latitude": p.get("latitude"),
                "longitude": p.get("longitude"),
            }
        )
    return rows


def to_csv(places: list[dict]) -> bytes:
    df = pd.DataFrame(_normalize_rows(places))
    columns = [
        "name",
        "category",
        "address",
        "phone",
        "email",
        "rating",
        "open_hours",
        "website",
        "maps_url",
        "province",
        "regency",
        "district",
        "latitude",
        "longitude",
    ]
    df = df.reindex(columns=columns)
    return df.to_csv(index=False).encode("utf-8-sig")


def to_excel(places: list[dict]) -> bytes:
    df = pd.DataFrame(_normalize_rows(places))
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Hasil Pencarian")
    buf.seek(0)
    return buf.getvalue()
