import os
import tempfile
import pytest

# Set test environment BEFORE any app modules are imported
_tmpdir = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_tmpdir}/test.db")
os.environ.setdefault("VAULT_PATH", _tmpdir)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("CHROMADB_PATH", f"{_tmpdir}/chroma")


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
