from pathlib import Path

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse

from budgetcare.db.uow import uow_factory
from budgetcare.services.dashboard import get_dashboard_summary

router = APIRouter(tags=["dashboard"])

DASHBOARD_DIR = Path(__file__).resolve().parent.parent.parent / "dashboard"


def get_dashboard_file(filename: str) -> str:
    """Read a dashboard asset file from the dashboard directory."""
    path = DASHBOARD_DIR / filename
    return path.read_text(encoding="utf-8")


@router.get("/api/dashboard/stats")
async def get_dashboard_stats():
    """Return JSON metrics for the monitoring dashboard."""
    async with uow_factory() as uow:
        summary = await get_dashboard_summary(uow.session)
        return summary


@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard_page():
    """Render single-page monitoring dashboard UI."""
    return HTMLResponse(content=get_dashboard_file("index.html"))


@router.get("/dashboard/style.css")
async def get_dashboard_style():
    """Serve dashboard CSS stylesheet."""
    return Response(content=get_dashboard_file("style.css"), media_type="text/css")


@router.get("/dashboard/app.js")
async def get_dashboard_script():
    """Serve dashboard client-side JavaScript."""
    return Response(
        content=get_dashboard_file("app.js"), media_type="application/javascript"
    )
