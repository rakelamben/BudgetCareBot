from typing import Any

from fastapi import APIRouter, Depends

from budgetcare.api.deps import verify_tick_secret
from budgetcare.services.tick import run_tick

router = APIRouter(tags=["tick"])


@router.post("/internal/tick", dependencies=[Depends(verify_tick_secret)])
async def trigger_tick() -> dict[str, Any]:
    """Execute scheduled tick cron job."""
    stats = await run_tick()
    return stats.to_dict()
