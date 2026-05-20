import json
import pytest
from pathlib import Path


async def test_create_admin_creates_user_with_admin_role():
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import select
    import manage

    await create_db()
    await manage.cmd_create_admin("manage-create@example.com", "password123")

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == "manage-create@example.com"))
        user = result.scalar_one_or_none()

    assert user is not None
    assert user.role == "admin"
    assert user.is_active is True
    assert user.is_superuser is False


async def test_create_admin_is_idempotent():
    import auth.users  # noqa: F401
    from db.database import create_db
    import manage

    await create_db()
    await manage.cmd_create_admin("manage-idempotent@example.com", "password123")
    await manage.cmd_create_admin("manage-idempotent@example.com", "password123")


async def test_create_admin_password_is_hashed():
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import select
    import manage

    await create_db()
    await manage.cmd_create_admin("manage-hashed@example.com", "password123")

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == "manage-hashed@example.com"))
        user = result.scalar_one_or_none()

    assert user.hashed_password != "password123"
    # Accept argon2 ($argon2id$) or bcrypt ($2b$) depending on the PasswordHelper backend
    assert user.hashed_password.startswith("$")


async def test_export_users_writes_json(tmp_path):
    import auth.users  # noqa: F401
    from db.database import create_db
    import manage

    await create_db()
    await manage.cmd_create_admin("manage-export@example.com", "secret")
    output = str(tmp_path / "users.json")
    await manage.cmd_export_users(output)

    data = json.loads(Path(output).read_text())
    # Filter to just the user we created — the shared DB may have users from other tests
    matches = [u for u in data if u["email"] == "manage-export@example.com"]
    assert len(matches) == 1
    assert matches[0]["role"] == "admin"
    assert "hashed_password" in matches[0]
    assert matches[0]["hashed_password"] != "secret"


async def test_export_users_empty_db_writes_empty_list(tmp_path):
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import delete
    import manage

    await create_db()
    # Ensure no users exist for this test (DB is shared across tests in the session)
    async with async_session_maker() as session:
        await session.execute(delete(User))
        await session.commit()

    output = str(tmp_path / "users.json")
    await manage.cmd_export_users(output)

    data = json.loads(Path(output).read_text())
    assert data == []


async def test_import_users_skips_existing(tmp_path):
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import select, delete
    import manage

    await create_db()
    # Isolate: clear users, create exactly one, export, re-import (should skip)
    async with async_session_maker() as session:
        await session.execute(delete(User))
        await session.commit()

    await manage.cmd_create_admin("manage-skip@example.com", "secret")
    export_file = str(tmp_path / "users.json")
    await manage.cmd_export_users(export_file)

    imported, skipped = await manage.cmd_import_users(export_file)
    assert imported == 0
    assert skipped == 1

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == "manage-skip@example.com"))
        user = result.scalar_one_or_none()
    assert user is not None


async def test_import_users_missing_file(tmp_path):
    import auth.users  # noqa: F401
    from db.database import create_db
    import manage

    await create_db()
    result = await manage.cmd_import_users(str(tmp_path / "nonexistent.json"))
    assert result == (0, 0)


async def test_import_users_inserts_new_users(tmp_path):
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import select, delete
    import manage

    await create_db()
    # Isolate: clear users, create one, export, clear again, re-import
    async with async_session_maker() as session:
        await session.execute(delete(User))
        await session.commit()

    await manage.cmd_create_admin("manage-insert@example.com", "secret")
    export_file = str(tmp_path / "users.json")
    await manage.cmd_export_users(export_file)

    async with async_session_maker() as session:
        await session.execute(delete(User))
        await session.commit()

    imported, skipped = await manage.cmd_import_users(export_file)
    assert imported == 1
    assert skipped == 0

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == "manage-insert@example.com"))
        user = result.scalar_one_or_none()
    assert user is not None
    assert user.role == "admin"

    # Teardown: remove only the user created by this test
    async with async_session_maker() as session:
        await session.execute(delete(User).where(User.email == "manage-insert@example.com"))
        await session.commit()


async def test_reset_password_updates_hash():
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from fastapi_users.password import PasswordHelper
    from sqlalchemy import select
    import manage

    await create_db()
    await manage.cmd_create_admin("manage-reset-hash@example.com", "oldpassword1")

    await manage.cmd_reset_password("manage-reset-hash@example.com", "newpassword1")

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == "manage-reset-hash@example.com"))
        user = result.scalar_one_or_none()

    ph = PasswordHelper()
    verified, _ = ph.verify_and_update("newpassword1", user.hashed_password)
    assert verified is True
    old_verified, _ = ph.verify_and_update("oldpassword1", user.hashed_password)
    assert old_verified is False


async def test_reset_password_with_role_change():
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from fastapi_users.password import PasswordHelper
    from sqlalchemy import select
    import manage

    await create_db()
    await manage.cmd_create_admin("manage-reset-role@example.com", "oldpassword1")

    await manage.cmd_reset_password("manage-reset-role@example.com", "newpassword1", role="reader")

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == "manage-reset-role@example.com"))
        user = result.scalar_one_or_none()

    assert user.role == "reader"
    ph = PasswordHelper()
    verified, _ = ph.verify_and_update("newpassword1", user.hashed_password)
    assert verified is True


async def test_reset_password_keeps_role_when_not_specified():
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import select
    import manage

    await create_db()
    await manage.cmd_create_admin("manage-reset-keeprole@example.com", "oldpassword1")

    await manage.cmd_reset_password("manage-reset-keeprole@example.com", "newpassword1")

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == "manage-reset-keeprole@example.com"))
        user = result.scalar_one_or_none()

    assert user.role == "admin"


async def test_reset_password_user_not_found():
    import auth.users  # noqa: F401
    from db.database import create_db
    import manage
    import pytest

    await create_db()
    with pytest.raises(SystemExit) as exc_info:
        await manage.cmd_reset_password("no-such-user@example.com", "newpassword1")
    assert exc_info.value.code == 1


async def test_reset_password_short_password():
    import auth.users  # noqa: F401
    from db.database import create_db
    import manage
    import pytest

    await create_db()
    await manage.cmd_create_admin("manage-reset-short@example.com", "oldpassword1")
    with pytest.raises(SystemExit) as exc_info:
        await manage.cmd_reset_password("manage-reset-short@example.com", "short")
    assert exc_info.value.code == 1
