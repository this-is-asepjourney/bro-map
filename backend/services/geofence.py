from sqlalchemy import text

from database import async_session


async def filter_by_boundary(
    places: list[dict],
    province: str,
    regency: str,
    district: str,
) -> list[dict]:
    """Filter places yang berada dalam batas kecamatan (PostGIS), jika boundary tersedia."""
    async with async_session() as session:
        check = await session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM regions r_d
                    WHERE r_d.level = 'district'
                      AND r_d.name ILIKE :district
                      AND EXISTS (
                        SELECT 1 FROM regions r_r
                        WHERE r_r.id = r_d.parent_id
                          AND r_r.level = 'regency'
                          AND r_r.name ILIKE :regency
                          AND EXISTS (
                            SELECT 1 FROM regions r_p
                            WHERE r_p.id = r_r.parent_id
                              AND r_p.level = 'province'
                              AND r_p.name ILIKE :province
                          )
                      )
                )
                """
            ),
            {
                "district": f"%{district.strip()}%",
                "regency": f"%{regency.strip()}%",
                "province": f"%{province.strip()}%",
            },
        )
        has_region = bool(check.scalar())

    if not has_region:
        return places

    filtered: list[dict] = []
    async with async_session() as session:
        for p in places:
            lat, lng = p.get("latitude"), p.get("longitude")
            if lat is None or lng is None:
                filtered.append(p)
                continue
            res = await session.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM regions r_d
                        WHERE r_d.level = 'district'
                          AND r_d.name ILIKE :district
                          AND EXISTS (
                            SELECT 1 FROM regions r_r
                            WHERE r_r.id = r_d.parent_id
                              AND r_r.level = 'regency'
                              AND r_r.name ILIKE :regency
                              AND EXISTS (
                                SELECT 1 FROM regions r_p
                                WHERE r_p.id = r_r.parent_id
                                  AND r_p.level = 'province'
                                  AND r_p.name ILIKE :province
                              )
                          )
                          AND ST_Covers(
                              r_d.boundary,
                              ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
                          )
                    )
                    """
                ),
                {
                    "lat": float(lat),
                    "lng": float(lng),
                    "district": f"%{district.strip()}%",
                    "regency": f"%{regency.strip()}%",
                    "province": f"%{province.strip()}%",
                },
            )
            if res.scalar():
                filtered.append(p)

    return filtered
