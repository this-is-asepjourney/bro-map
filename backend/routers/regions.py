from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from database import async_session
from models.region import Region

router = APIRouter(prefix="/api", tags=["regions"])


@router.get("/regions")
async def list_regions(
    level: str = Query(..., pattern="^(province|regency|district)$"),
    parent: str | None = Query(None, description="Nama provinsi (untuk regency) atau kab/kota (untuk district)"),
):
    async with async_session() as session:
        if level == "province":
            result = await session.execute(
                select(Region.id, Region.name)
                .where(Region.level == "province", Region.name.isnot(None))
                .order_by(Region.name)
            )
            rows = result.all()
            return {"level": level, "items": [{"id": r.id, "name": r.name} for r in rows]}

        if not parent:
            raise HTTPException(status_code=400, detail="Parameter 'parent' wajib untuk level regency dan district")

        if level == "regency":
            subq = select(Region.id).where(
                Region.level == "province",
                Region.name.ilike(f"%{parent.strip()}%"),
            )
            result = await session.execute(
                select(Region.id, Region.name)
                .where(Region.level == "regency", Region.parent_id.in_(subq), Region.name.isnot(None))
                .order_by(Region.name)
            )
        else:
            subq = select(Region.id).where(
                Region.level == "regency",
                Region.name.ilike(f"%{parent.strip()}%"),
            )
            result = await session.execute(
                select(Region.id, Region.name)
                .where(Region.level == "district", Region.parent_id.in_(subq), Region.name.isnot(None))
                .order_by(Region.name)
            )

        rows = result.all()
        return {"level": level, "parent": parent, "items": [{"id": r.id, "name": r.name} for r in rows]}
