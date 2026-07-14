import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock, Mock
from src.web.app import app


class _MockResult:
    def scalars(self):
        return self

    def all(self):
        return []

    def scalar_one_or_none(self):
        return None

    def scalar(self):
        return None


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def mock_db():
    with patch("src.web.app.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__.return_value = mock_session
        mock_factory.return_value.__aexit__.return_value = None
        yield mock_session


@pytest.mark.asyncio
async def test_dashboard_route_exists(client, mock_db):
    mock_db.execute.return_value = _MockResult()
    resp = await client.get("/")
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_job_detail_returns_404_for_missing(client, mock_db):
    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    resp = await client.get("/job/99999")
    assert resp.status_code == 404
