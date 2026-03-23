import pytest
import importlib


def test_weak_secret_key_raises_on_startup(monkeypatch):
    """Settings should refuse to construct with a short or default SECRET_KEY."""
    monkeypatch.setenv("SECRET_KEY", "tooshort")
    import config
    with pytest.raises((ValueError, RuntimeError)):
        importlib.reload(config)


def test_changeme_secret_key_raises_on_startup(monkeypatch):
    """Settings should reject 'changeme' as SECRET_KEY."""
    monkeypatch.setenv("SECRET_KEY", "changeme")
    import config
    with pytest.raises((ValueError, RuntimeError)):
        importlib.reload(config)
