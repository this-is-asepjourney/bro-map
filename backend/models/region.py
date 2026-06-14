from geoalchemy2 import Geography
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    boundary = mapped_column(Geography(geometry_type="MULTIPOLYGON", srid=4326), nullable=False)

    parent = relationship("Region", remote_side="Region.id", backref="children")
