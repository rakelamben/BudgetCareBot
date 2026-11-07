from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text

from budgetcare.db.uow import uow_factory

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(deep: int = Query(default=0)) -> dict:
    if deep == 1:
        try:
            async with uow_factory() as uow:
                await uow.session.execute(text("SELECT 1"))
            return {"status": "ok", "deep": True, "database": "connected"}
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "unhealthy", "database": "disconnected", "error": str(e)},
            ) from e
    return {"status": "ok"}

