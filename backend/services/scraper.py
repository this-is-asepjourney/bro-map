"""Integrasi Google Maps Platform — Places API (New).

Dokumentasi resmi:
- Text Search (New):  https://developers.google.com/maps/documentation/places/web-service/text-search
- Field Mask:         https://developers.google.com/maps/documentation/places/web-service/choose-fields

Endpoint utama:
    POST https://places.googleapis.com/v1/places:searchText

Header wajib:
    X-Goog-Api-Key: <API_KEY>
    X-Goog-FieldMask: places.id,places.displayName,...
    Content-Type: application/json
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Maks. results per halaman menurut Google Places API (New).
_PAGE_SIZE = 20
# Google saat ini hanya mengirim hingga 3 halaman (60 hasil).
_MAX_PAGES = 3

# Daftar field yang diminta dari Google. Field mask wajib supaya respons
# tidak default ke semua field (yang lebih mahal).
_PLACE_FIELDS = (
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.rating",
    "places.userRatingCount",
    "places.googleMapsUri",
    "places.internationalPhoneNumber",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.regularOpeningHours",
    "places.types",
    "places.primaryType",
    "nextPageToken",
)


def _normalize_opening_hours(raw: dict | None) -> dict | None:
    """Ubah `regularOpeningHours.weekdayDescriptions` jadi dict yang JSON-friendly."""
    if not raw or not isinstance(raw, dict):
        return None
    weekday = raw.get("weekdayDescriptions")
    if isinstance(weekday, list) and weekday:
        # Format: ["Senin: 08.00–17.00", "Selasa: ...", ...]
        out: dict[str, str] = {}
        for entry in weekday:
            if not isinstance(entry, str):
                continue
            if ":" in entry:
                day, hours = entry.split(":", 1)
                out[day.strip().lower()] = hours.strip()
            else:
                out[str(len(out))] = entry
        return out or None
    return None


def _normalize_place(place: dict[str, Any]) -> dict[str, Any]:
    """Ubah satu hasil Places API (New) jadi shape yang dipakai backend kita."""
    display = place.get("displayName") or {}
    name = display.get("text") if isinstance(display, dict) else None

    location = place.get("location") or {}
    lat = location.get("latitude")
    lng = location.get("longitude")

    phone = place.get("internationalPhoneNumber") or place.get("nationalPhoneNumber")

    return {
        "place_id": place.get("id"),
        "name": name,
        "address": place.get("formattedAddress"),
        "rating": place.get("rating"),
        "total_reviews": place.get("userRatingCount"),
        "maps_url": place.get("googleMapsUri"),
        "latitude": float(lat) if lat is not None else None,
        "longitude": float(lng) if lng is not None else None,
        "phone": phone,
        "website": place.get("websiteUri"),
        "open_hours": _normalize_opening_hours(place.get("regularOpeningHours")),
        "email": None,  # Google Places tidak menyediakan email
        "google_types": place.get("types") or [],
        "primary_type": place.get("primaryType"),
    }


async def search_google_maps(keyword: str, max_results: int = 20) -> list[dict[str, Any]]:
    """Cari tempat via Google Places API (New) — Text Search.

    Menggabungkan beberapa halaman (pageToken) supaya bisa mengembalikan
    hingga ``max_results`` item (dibatasi oleh ``MAX_RESULTS_LIMIT`` di settings
    dan kapasitas Google ±60 hasil).
    """
    if not settings.GOOGLE_MAPS_API_KEY:
        logger.warning("GOOGLE_MAPS_API_KEY belum diatur; lewati pencarian Google Places.")
        return []

    target = max(1, min(int(max_results), settings.MAX_RESULTS_LIMIT))
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": ",".join(_PLACE_FIELDS),
    }

    results: list[dict[str, Any]] = []
    page_token: str | None = None

    async with httpx.AsyncClient(timeout=60.0) as client:
        for page in range(_MAX_PAGES):
            remaining = target - len(results)
            if remaining <= 0:
                break

            body: dict[str, Any] = {
                "textQuery": keyword,
                "languageCode": "id",
                "regionCode": "ID",
                "maxResultCount": min(remaining, _PAGE_SIZE),
            }
            if page_token:
                body["pageToken"] = page_token

            try:
                resp = await client.post(PLACES_TEXT_SEARCH_URL, headers=headers, json=body)
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "Google Places searchText gagal (%s): %s",
                    e.response.status_code,
                    (e.response.text or "")[:300],
                )
                if not results:
                    raise
                break
            except httpx.RequestError as e:
                logger.warning("Google Places request error: %s", e)
                if not results:
                    raise
                break

            data = resp.json() or {}
            places = data.get("places") or []
            for p in places:
                results.append(_normalize_place(p))
                if len(results) >= target:
                    break

            page_token = data.get("nextPageToken")
            if not page_token or len(results) >= target:
                break

            # Page token baru butuh sedikit waktu sebelum aktif.
            await asyncio.sleep(1.2)

    return results[:target]


async def get_place_detail(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Backwards-compat stub.

    Places API (New) sudah mengembalikan detail (phone, website, opening hours)
    pada respons Text Search via field mask, jadi pemanggilan detail terpisah
    tidak diperlukan lagi.
    """
    return {
        "phone": None,
        "website": None,
        "open_hours": None,
        "email": None,
    }
