import os
import tempfile
import pytest

# Set test environment BEFORE any app modules are imported
_tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmpdir}/test.db"
os.environ["VAULT_PATH"] = _tmpdir
os.environ.setdefault("SECRET_KEY", "test-secret-key-placeholder-32ch")  # must be >=32 chars
os.environ["CHROMADB_PATH"] = f"{_tmpdir}/chroma"


@pytest.fixture(autouse=True)
async def reset_db():
    """Reset the lazy DB engine between tests so each test gets a clean state."""
    import db.database as _db
    _db._engine = None
    _db._maker = None
    yield
    if _db._engine:
        await _db._engine.dispose()
    _db._engine = None
    _db._maker = None


async def create_test_user(email: str, password: str, role: str) -> None:
    """Create a user directly in the DB with the specified role.

    Bypasses the /auth/register endpoint (which now forces role=reader via on_after_register).
    Use this in fixtures that need editor or admin access.
    """
    import auth.users  # noqa: F401 — ensures User model is registered with Base
    from db.database import create_db, async_session_maker
    from auth.users import User
    from fastapi_users.password import PasswordHelper

    await create_db()
    ph = PasswordHelper()
    hashed = ph.hash(password)
    async with async_session_maker() as session:
        user = User(
            email=email,
            hashed_password=hashed,
            role=role,
            is_active=True,
            is_superuser=False,
            is_verified=False,
        )
        session.add(user)
        await session.commit()
