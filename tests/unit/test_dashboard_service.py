import sys
import unittest
from unittest.mock import MagicMock

# Mock third-party dependencies if not installed
for mod in [
    "aiogram",
    "aiogram.filters",
    "aiogram.types",
    "fastapi",
    "fastapi.responses",
    "sqlalchemy",
    "sqlalchemy.orm",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.dialects",
    "sqlalchemy.dialects.postgresql",
    "pydantic",
    "pydantic_settings",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

# Preserve decorated functions when mocking APIRouter
def mock_route_decorator(*args, **kwargs):
    def wrapper(fn):
        return fn
    return wrapper

mock_router = MagicMock()
mock_router.get = mock_route_decorator
mock_router.post = mock_route_decorator
sys.modules["fastapi"].APIRouter = lambda *a, **kw: mock_router

# Configure Response and HTMLResponse mocks
class DummyResponse:
    def __init__(self, content, status_code=200, media_type=None):
        self.content = content
        self.status_code = status_code
        self.media_type = media_type

class DummyHTMLResponse(DummyResponse):
    def __init__(self, content, status_code=200, media_type="text/html"):
        super().__init__(content, status_code, media_type)

sys.modules["fastapi"].Response = DummyResponse
sys.modules["fastapi.responses"].HTMLResponse = DummyHTMLResponse

from budgetcare.api.routes.dashboard import (
    get_dashboard_file,
    get_dashboard_page,
    get_dashboard_script,
    get_dashboard_style,
)


class TestDashboardService(unittest.TestCase):
    def test_dashboard_file_loading(self):
        """Verify HTML, CSS, and JS files can be loaded from the dedicated directory."""
        html = get_dashboard_file("index.html")
        css = get_dashboard_file("style.css")
        js = get_dashboard_file("app.js")

        # HTML assertions
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("/dashboard/style.css", html)
        self.assertIn("/dashboard/app.js", html)
        self.assertIn("Budget Care", html)

        # CSS assertions
        self.assertIn(".tab-btn.active", css)
        self.assertIn("font-family", css)

        # JS assertions
        self.assertIn("fetchStats", js)
        self.assertIn("/api/dashboard/stats", js)
        self.assertIn("renderDashboard", js)

    async def _async_test_routes(self):
        html_res = await get_dashboard_page()
        self.assertEqual(html_res.status_code, 200)
        self.assertEqual(html_res.media_type, "text/html")
        self.assertIn("Budget Care", html_res.content)

        css_res = await get_dashboard_style()
        self.assertEqual(css_res.status_code, 200)
        self.assertEqual(css_res.media_type, "text/css")
        self.assertIn(".tab-btn.active", css_res.content)

        js_res = await get_dashboard_script()
        self.assertEqual(js_res.status_code, 200)
        self.assertEqual(js_res.media_type, "application/javascript")
        self.assertIn("fetchStats", js_res.content)

    def test_dashboard_endpoint_responses(self):
        import asyncio
        asyncio.run(self._async_test_routes())


if __name__ == "__main__":
    unittest.main()
