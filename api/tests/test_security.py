import pytest


async def test_weak_secret_key_raises_on_startup(monkeypatch):
    """Settings should refuse to construct with a short or default SECRET_KEY."""
    from config import Settings

    monkeypatch.setenv("SECRET_KEY", "tooshort")
    with pytest.raises(ValueError, match="SECRET_KEY is insecure"):
        Settings()


async def test_changeme_secret_key_raises_on_startup(monkeypatch):
    """Settings should reject 'changeme' as SECRET_KEY."""
    from config import Settings

    monkeypatch.setenv("SECRET_KEY", "changeme")
    with pytest.raises(ValueError, match="SECRET_KEY is insecure"):
        Settings()
