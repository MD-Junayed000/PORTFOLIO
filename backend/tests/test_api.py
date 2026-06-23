import pytest
from httpx import AsyncClient, ASGITransport
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test environment variables BEFORE importing the app.
# Use the in-memory asyncpg-compatible engine (Neon provides this via DATABASE_URL
# in CI). For local tests, set DATABASE_URL in the environment to a Postgres URL
# (e.g. a local docker postgres) — SQLite is no longer supported because the
# real architecture uses asyncpg + pgvector.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_portfolio.db")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "test-cloud")
os.environ.setdefault("CLOUDINARY_API_KEY", "test-key")
os.environ.setdefault("CLOUDINARY_API_SECRET", "test-secret")

from main import app
from database import engine
from services.vector_store import initialize_collection
from services.seed_data import seed_database


@pytest.fixture(autouse=True)
async def setup_db():
    """Initialize database and vector store before tests.

    The schema is created by Alembic migrations in production; for tests we
    simply ensure the vector collection wrapper is ready. RAG ingestion is
    MANUAL only — no automatic seeding happens.
    """
    initialize_collection()
    await seed_database()
    yield
    # Cleanup test database
    if os.path.exists("./test_portfolio.db"):
        try:
            os.remove("./test_portfolio.db")
        except OSError:
            pass
    await engine.dispose()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.anyio
async def test_login_success():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Use default credentials
        response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.anyio
async def test_login_failure():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrongpassword"},
        )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_admin_route_requires_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/admin/about",
            json={"bio": "test", "title": "test"},
        )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_get_about():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/about")
    assert response.status_code == 200
    data = response.json()
    assert "bio" in data
    assert "title" in data


@pytest.mark.anyio
async def test_get_projects():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/projects")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.anyio
async def test_get_skills():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/skills")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.anyio
async def test_get_research():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/research")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.anyio
async def test_chat_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            json={"message": "Tell me about Muhammad Junayed"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert isinstance(data["response"], str)
    assert len(data["response"]) > 0


@pytest.mark.anyio
async def test_verify_token_invalid():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/auth/verify",
            headers={"Authorization": "Bearer invalid-token"},
        )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_verify_token_valid():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login first
        login_response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        token = login_response.json()["access_token"]

        # Verify token
        response = await client.get(
            "/api/auth/verify",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "valid"


@pytest.mark.anyio
async def test_get_experiences():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/experiences")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.anyio
async def test_post_contact():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/contact",
            json={
                "name": "Test User",
                "email": "test@example.com",
                "message": "Hello, this is a test message.",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test User"
    assert data["email"] == "test@example.com"
    assert data["message"] == "Hello, this is a test message."
    assert "id" in data


@pytest.mark.anyio
async def test_get_admin_database():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login first
        login_response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        token = login_response.json()["access_token"]

        # Get database info
        response = await client.get(
            "/api/admin/database",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "tables" in data
    assert isinstance(data["tables"], list)
    # Should have at least the core tables
    table_names = [t["name"] for t in data["tables"]]
    assert "projects" in table_names
    assert "contact_messages" in table_names
    assert "documents" in table_names


@pytest.mark.anyio
async def test_admin_experiences_crud():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login first
        login_response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create experience
        response = await client.post(
            "/api/admin/experiences",
            json={
                "title": "Software Engineer",
                "organization": "Test Corp",
                "period": "2022-2023",
                "description": "Built things",
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Software Engineer"
        exp_id = data["id"]

        # Update experience
        response = await client.put(
            f"/api/admin/experiences/{exp_id}",
            json={
                "title": "Senior Software Engineer",
                "organization": "Test Corp",
                "period": "2022-2024",
                "description": "Built more things",
            },
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Senior Software Engineer"

        # Delete experience
        response = await client.delete(
            f"/api/admin/experiences/{exp_id}",
            headers=headers,
        )
        assert response.status_code == 200


@pytest.mark.anyio
async def test_admin_messages():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First create a contact message
        await client.post(
            "/api/contact",
            json={
                "name": "Msg User",
                "email": "msg@example.com",
                "message": "Test message for admin",
            },
        )

        # Login
        login_response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # List messages
        response = await client.get("/api/admin/messages", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        # Delete message
        msg_id = data[0]["id"]
        response = await client.delete(
            f"/api/admin/messages/{msg_id}", headers=headers
        )
        assert response.status_code == 200


@pytest.mark.anyio
async def test_admin_settings_get():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login
        login_response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Get settings
        response = await client.get("/api/admin/settings", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "hf_model_id" in data
        assert "has_token" in data
