from pydantic import BaseModel, ConfigDict, Field, field_validator


class SearchRequest(BaseModel):
    category: str = Field(..., description="Kategori bisnis")
    keyword: str = Field(..., min_length=1)
    province: str = Field(..., min_length=1)
    regency: str = Field(..., min_length=1)
    district: str = Field(..., min_length=1)
    max_results: int = Field(default=20, ge=1, le=50)

    @field_validator("max_results")
    @classmethod
    def cap_max(cls, v: int) -> int:
        from config import settings

        return min(v, settings.MAX_RESULTS_LIMIT)


class PlaceResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    rating: float | None = None
    total_reviews: int | None = None
    open_hours: dict | list | None = None
    website: str | None = None
    maps_url: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    category: str | None = None
    province: str | None = None
    regency: str | None = None
    district: str | None = None


class SearchResponse(BaseModel):
    total: int
    query: str
    results: list[PlaceResult]
    search_id: str | None = None
    cached: bool = False
