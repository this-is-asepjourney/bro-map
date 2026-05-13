from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import JSON, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    rating: Mapped[float | None] = mapped_column(Numeric(2, 1), nullable=True)
    total_reviews: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    maps_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    location = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    regency: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    search_query: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
