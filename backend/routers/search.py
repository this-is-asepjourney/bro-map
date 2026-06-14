import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from geoalchemy2.elements import WKTElement
from sqlalchemy import text

from config import settings
from database import async_session
from models.place import Place
from routers.export import store_export_payload
from schemas.search import PlaceResult, SearchRequest, SearchResponse
from services.geofence import filter_by_boundary
from services.scraper import get_place_detail, search_google_maps

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["search"])


def _build_query(req: SearchRequest) -> str:
    return f"{req.keyword.strip()} {req.district.strip()} {req.regency.strip()} {req.province.strip()}"


async def _load_cached(session, query_str: str, limit: int) -> list[dict] | None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.CACHE_TTL_HOURS)
    sql = text(
        """
        SELECT name, category, address, phone, email, rating, total_reviews,
               open_hours, website, maps_url,
               ST_Y(location::geometry) AS latitude,
               ST_X(location::geometry) AS longitude,
               province, regency, district, search_query
        FROM places
        WHERE search_query = :sq AND scraped_at >= :cutoff
        ORDER BY id DESC
        LIMIT :lim
        """
    )
    result = await session.execute(
        sql,
        {"sq": query_str, "cutoff": cutoff, "lim": limit},
    )
    rows = result.mappings().all()
    if not rows:
        return None
    return [dict(r) for r in rows]


async def _save_places(session, query_str: str, items: list[dict]) -> None:
    for row in items:
        lat, lng = row.get("latitude"), row.get("longitude")
        loc = None
        if lat is not None and lng is not None:
            loc = WKTElement(f"POINT({float(lng)} {float(lat)})", srid=4326)
        place = Place(
            name=row.get("name") or "Tanpa nama",
            category=row.get("category"),
            address=row.get("address"),
            phone=row.get("phone"),
            email=row.get("email"),
            rating=row.get("rating"),
            total_reviews=row.get("total_reviews"),
            open_hours=row.get("open_hours") if isinstance(row.get("open_hours"), dict) else row.get("open_hours"),
            website=row.get("website"),
            maps_url=row.get("maps_url"),
            location=loc,
            province=row.get("province"),
            regency=row.get("regency"),
            district=row.get("district"),
            search_query=query_str,
        )
        session.add(place)
    await session.commit()


@router.post("/search", response_model=SearchResponse)
async def search_places(req: SearchRequest, request: Request):
    query = _build_query(req)

    async with async_session() as session:
        cached = await _load_cached(session, query, req.max_results)
        if cached is not None and len(cached) > 0:
            results = [PlaceResult.model_validate(r) for r in cached]
            sid = store_export_payload(request, [m.model_dump() for m in results])
            return SearchResponse(
                total=len(results),
                query=query,
                results=results,
                search_id=sid,
                cached=True,
            )

    if not (settings.GOOGLE_MAPS_API_KEY or "").strip():
        raise HTTPException(
            status_code=503,
            detail="GOOGLE_MAPS_API_KEY belum diatur. Tambahkan di file .env (aktifkan Places API di Google Cloud).",
        )

    try:
        raw_results = await search_google_maps(query, req.max_results)
    except httpx.HTTPStatusError as e:
        logger.exception("Google Places HTTP error")
        body = (e.response.text or "")[:400]
        raise HTTPException(
            status_code=502,
            detail=f"Google Places API error {e.response.status_code}: {body or e.response.reason_phrase}",
        ) from e
    except httpx.RequestError as e:
        logger.exception("Google Places request failed")
        raise HTTPException(status_code=502, detail=f"Gagal menghubungi Google Places: {e!s}") from e

    enriched: list[dict] = []
    for r in raw_results:
        data_id = r.get("data_id")
        if isinstance(data_id, dict):
            data_id = data_id.get("data_id") or data_id.get("value")
        data_id = str(data_id).strip() if data_id else ""
        place_id_raw = r.get("place_id")
        place_id = str(place_id_raw).strip() if place_id_raw else None
        gps = r.get("gps_coordinates") or {}
        lat, lng = gps.get("latitude"), gps.get("longitude")
        detail = await get_place_detail(
            data_id,
            place_id=place_id,
            latitude=float(lat) if lat is not None else None,
            longitude=float(lng) if lng is not None else None,
        )
        enriched.append(
            {
                "name": r.get("title"),
                "address": r.get("address"),
                "rating": r.get("rating"),
                "total_reviews": r.get("reviews"),
                "maps_url": r.get("link") or r.get("gps_coordinates", {}).get("link"),
                "latitude": gps.get("latitude"),
                "longitude": gps.get("longitude"),
                "category": req.category,
                "province": req.province,
                "regency": req.regency,
                "district": req.district,
                **detail,
            }
        )

    filtered = await filter_by_boundary(enriched, req.province, req.regency, req.district)

    async with async_session() as session:
        try:
            await _save_places(session, query, filtered)
        except Exception:
            logger.exception("Gagal menyimpan places ke database")
            # tetap kembalikan hasil meski persist gagal

    results = [PlaceResult.model_validate(p) for p in filtered]
    sid = store_export_payload(request, [m.model_dump() for m in results])

    return SearchResponse(
        total=len(results),
        query=query,
        results=results,
        search_id=sid,
        cached=False,
    )
