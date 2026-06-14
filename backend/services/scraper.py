import logging
import re
from html import unescape
from urllib.parse import quote

import httpx

from config import settings

logger = logging.getLogger(__name__)

PLACES_TEXT_SEARCH = "https://places.googleapis.com/v1/places:searchText"
SEARCH_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.location,"
    "places.rating,places.userRatingCount,places.types,places.googleMapsUri"
)
DETAIL_FIELD_MASK = (
    "internationalPhoneNumber,nationalPhoneNumber,websiteUri,regularOpeningHours"
)

MAILTO_RE = re.compile(r'mailto:([^"\'\s<>&]+)', re.IGNORECASE)
EMAIL_RE = re.compile(
    r"[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}",
)
_BAD_EMAIL_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".css",
    ".js",
    ".woff",
    ".woff2",
    ".ico",
)


def _api_key() -> str:
    return (settings.GOOGLE_MAPS_API_KEY or "").strip()


def _empty_detail() -> dict:
    return {
        "phone": None,
        "website": None,
        "open_hours": None,
        "email": None,
    }


def _merge_phone(intl: str | None, national: str | None) -> str | None:
    a = (intl or "").strip()
    b = (national or "").strip()
    return a or b or None


def _is_plausible_business_email(addr: str) -> bool:
    al = addr.lower().strip()
    if "@" not in al:
        return False
    for suf in _BAD_EMAIL_SUFFIXES:
        if al.endswith(suf):
            return False
    if al.endswith("@2x.png") or "@sentry" in al or "wixpress.com" in al:
        return False
    if "example.com" in al or "yoursite.com" in al or "domain.com" in al:
        return False
    return True


def _clean_mailto_fragment(raw: str) -> str | None:
    addr = unescape(raw.split("?", maxsplit=1)[0]).strip()
    addr = addr.strip("/")
    if not addr or "@" not in addr:
        return None
    return addr if _is_plausible_business_email(addr) else None


def _extract_email_from_html(html: str) -> str | None:
    """Ambil satu alamat email dari HTML (mailto: lalu fallback regex)."""
    snippet = html[:250_000]
    for m in MAILTO_RE.finditer(snippet):
        cleaned = _clean_mailto_fragment(m.group(1))
        if cleaned:
            return cleaned
    for m in EMAIL_RE.finditer(snippet):
        candidate = m.group(0).strip()
        if _is_plausible_business_email(candidate):
            return candidate
    return None


async def _fetch_email_from_website(client: httpx.AsyncClient, website_url: str) -> str | None:
    u = (website_url or "").strip()
    if not u.startswith(("http://", "https://")):
        return None
    try:
        r = await client.get(
            u,
            timeout=12.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "id,en;q=0.9",
            },
        )
        r.raise_for_status()
        ct = (r.headers.get("content-type") or "").lower()
        if "html" not in ct and "text/plain" not in ct:
            return None
        return _extract_email_from_html(r.text)
    except Exception as e:
        logger.debug("Ekstraksi email dari %s gagal: %s", u[:96], e)
        return None


def _place_id_from_name(name: str | None) -> str:
    if not name:
        return ""
    n = name.strip()
    if n.startswith("places/"):
        return n.removeprefix("places/").strip("/")
    return n


def _normalize_places_api_place(place: dict) -> dict:
    """Samakan bentuk dengan hasil SerpAPI lama agar router tidak berubah banyak."""
    name = place.get("name") or ""
    place_id = _place_id_from_name(name)
    disp = place.get("displayName") or {}
    title = disp.get("text") if isinstance(disp, dict) else None
    loc = place.get("location") or {}
    lat, lng = loc.get("latitude"), loc.get("longitude")
    maps_uri = place.get("googleMapsUri")
    return {
        "title": title,
        "address": place.get("formattedAddress"),
        "rating": place.get("rating"),
        "reviews": place.get("userRatingCount"),
        "link": maps_uri,
        "place_id": place_id,
        "gps_coordinates": {
            "latitude": lat,
            "longitude": lng,
            "link": maps_uri,
        },
        "data_id": "",
    }


async def search_google_maps(keyword: str, max_results: int = 20) -> list[dict]:
    """Text Search (Places API New). Maks. 20 tempat per permintaan; pakai pageToken untuk lanjut."""
    key = _api_key()
    if not key:
        return []

    cap = min(max_results, settings.MAX_RESULTS_LIMIT)
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": SEARCH_FIELD_MASK,
    }

    out: list[dict] = []
    page_token: str | None = None

    async with httpx.AsyncClient(timeout=60.0) as client:
        while len(out) < cap:
            body: dict[str, object] = {
                "textQuery": keyword,
                "languageCode": "id",
                "regionCode": "ID",
                "maxResultCount": min(20, cap - len(out)),
            }
            if page_token:
                body["pageToken"] = page_token

            resp = await client.post(PLACES_TEXT_SEARCH, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            places = data.get("places") or []
            for p in places:
                out.append(_normalize_places_api_place(p))
                if len(out) >= cap:
                    break

            page_token = data.get("nextPageToken")
            if not page_token or not places:
                break

    return out[:cap]


async def get_place_detail(
    data_id: str,
    *,
    place_id: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict:
    """
    Detail tempat via Places API (New).
    Nomor: international + national (fallback). Email: tidak dari Google;
    opsional diambil dari HTML website bisnis bila EMAIL_SCRAPE_FROM_WEBSITE=true.
    """
    key = _api_key()
    if not key:
        return _empty_detail()

    pid = (place_id or "").strip()
    if not pid:
        return _empty_detail()

    encoded = quote(pid, safe="")
    places_url = f"https://places.googleapis.com/v1/places/{encoded}"
    places_headers = {
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": DETAIL_FIELD_MASK,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(places_url, headers=places_headers)
            resp.raise_for_status()
            place = resp.json()

            roh = place.get("regularOpeningHours") or {}
            weekdays = roh.get("weekdayDescriptions")
            open_hours = None
            if isinstance(weekdays, list) and weekdays:
                open_hours = {str(i): line for i, line in enumerate(weekdays)}

            website = place.get("websiteUri")
            phone = _merge_phone(
                place.get("internationalPhoneNumber"),
                place.get("nationalPhoneNumber"),
            )

            email = None
            if website and settings.EMAIL_SCRAPE_FROM_WEBSITE:
                email = await _fetch_email_from_website(client, website)

            return {
                "phone": phone,
                "website": website,
                "open_hours": open_hours,
                "email": email,
            }
    except httpx.HTTPStatusError as e:
        logger.warning(
            "Google Places detail gagal (%s): %s",
            e.response.status_code,
            (e.response.text or "")[:300],
        )
        return _empty_detail()
    except httpx.RequestError as e:
        logger.warning("Google Places detail request error: %s", e)
        return _empty_detail()
