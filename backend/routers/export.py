import time
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from services.exporter import to_csv, to_excel

router = APIRouter(prefix="/api", tags=["export"])

CACHE_TTL_SEC = 3600


def _cache_put(request: Request, places: list[dict]) -> str:
    sid = uuid.uuid4().hex
    cache: dict = request.app.state.export_cache
    cache[sid] = {"places": places, "expires": time.time() + CACHE_TTL_SEC}
    # prune old
    now = time.time()
    dead = [k for k, v in cache.items() if v.get("expires", 0) < now]
    for k in dead:
        cache.pop(k, None)
    return sid


def _cache_get(request: Request, search_id: str) -> list[dict]:
    cache: dict = request.app.state.export_cache
    entry = cache.get(search_id)
    if not entry:
        raise HTTPException(status_code=404, detail="search_id tidak ditemukan atau sudah kedaluwarsa")
    if entry.get("expires", 0) < time.time():
        cache.pop(search_id, None)
        raise HTTPException(status_code=404, detail="search_id kedaluwarsa")
    return entry["places"]


@router.get("/export")
async def export_results(
    request: Request,
    export_format: str = Query("csv", pattern="^(csv|xlsx)$", alias="format"),
    search_id: str = Query(..., min_length=8),
):
    places = _cache_get(request, search_id)
    if export_format == "csv":
        body = to_csv(places)
        return Response(
            content=body,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="hasil_pencarian.csv"'},
        )
    body = to_excel(places)
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="hasil_pencarian.xlsx"'},
    )


def store_export_payload(request: Request, places: list[dict]) -> str:
    return _cache_put(request, places)
