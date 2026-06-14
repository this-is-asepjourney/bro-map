from pydantic import BaseModel


class PlaceRead(BaseModel):
    id: int
    name: str
    category: str | None
    address: str | None
    phone: str | None
    email: str | None
    rating: float | None
    total_reviews: int | None
    open_hours: dict | list | None
    website: str | None
    maps_url: str | None
    province: str | None
    regency: str | None
    district: str | None

    class Config:
        from_attributes = True
