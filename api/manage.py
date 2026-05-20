#!/usr/bin/env python3
"""KMS management CLI — run inside the API container.

Usage:
    python manage.py create-admin --email X --password Y
    python manage.py export-users [--output /data/manage/users.json]
    python manage.py import-users [--input /data/manage/users.json]
"""
import argparse
import asyncio
import getpass
import json
import sys
from pathlib import Path


async def cmd_create_admin(email: str, password: str) -> None:
    import auth.users  # noqa: F401 — registers User with Base.metadata
    from db.database import create_db, async_session_maker
    from auth.users import User
    from fastapi_users.password import PasswordHelper
    from sqlalchemy import select
    import uuid

    await create_db()
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            print(f"User already exists: {email}")
            return
        ph = PasswordHelper()
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=ph.hash(password),
            role="admin",
            is_active=True,
            is_superuser=False,
            is_verified=False,
        )
        session.add(user)
        await session.commit()
    print(f"Admin created: {email}")


async def cmd_reset_password(email: str, password: str, role: str | None = None) -> None:
    import auth.users  # noqa: F401 — registers User with Base.metadata
    from db.database import create_db, async_session_maker
    from auth.users import User
    from fastapi_users.password import PasswordHelper
    from sqlalchemy import select, func

    if len(password) < 8:
        print("Password must be at least 8 characters")
        sys.exit(1)

    await create_db()
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(func.lower(User.email) == email.lower())
        )
        user = result.scalar_one_or_none()
        if not user:
            print(f"No user found with email: {email}")
            sys.exit(1)
        ph = PasswordHelper()
        user.hashed_password = ph.hash(password)
        if role is not None:
            user.role = role
        await session.commit()
        await session.refresh(user)
    print(f"Password reset for {user.email} (role: {user.role})")


async def cmd_export_users(output: str) -> None:
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import select

    await create_db()
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_session_maker() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        data = [
            {
                "id": str(u.id),
                "email": u.email,
                "hashed_password": u.hashed_password,
                "role": u.role,
                "is_active": u.is_active,
                "is_superuser": u.is_superuser,
                "is_verified": u.is_verified,
            }
            for u in users
        ]

    output_path.write_text(json.dumps(data, indent=2))
    print(f"Exported {len(data)} users to {output}")


async def cmd_import_users(input_path: str):
    import auth.users  # noqa: F401
    from db.database import create_db, async_session_maker
    from auth.users import User
    from sqlalchemy import select
    import uuid as uuid_mod

    path = Path(input_path)
    if not path.exists():
        print(f"Warning: {input_path} not found. Skipping import.")
        return (0, 0)

    await create_db()
    data = json.loads(path.read_text())

    imported = 0
    skipped = 0
    async with async_session_maker() as session:
        for u in data:
            try:
                result = await session.execute(select(User).where(User.email == u["email"]))
                if result.scalar_one_or_none():
                    skipped += 1
                    continue
                user = User(
                    id=uuid_mod.UUID(u["id"]),
                    email=u["email"],
                    hashed_password=u["hashed_password"],
                    role=u["role"],
                    is_active=u["is_active"],
                    is_superuser=u["is_superuser"],
                    is_verified=u["is_verified"],
                )
                session.add(user)
                imported += 1
            except (KeyError, ValueError) as e:
                print(f"Warning: skipping malformed record: {e}")
                skipped += 1
        await session.commit()

    print(f"Imported {imported} users, skipped {skipped} existing")
    return imported, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="KMS management commands")
    sub = parser.add_subparsers(dest="command", required=True)

    p_admin = sub.add_parser("create-admin", help="Create an admin user directly in the DB")
    p_admin.add_argument("--email", required=True, help="Admin email address")
    p_admin.add_argument("--password", required=True, help="Admin password (will be hashed)")

    p_export = sub.add_parser("export-users", help="Export all users to JSON")
    p_export.add_argument("--output", default="/data/manage/users.json")

    p_import = sub.add_parser("import-users", help="Import users from JSON (skips existing)")
    p_import.add_argument("--input", default="/data/manage/users.json")

    args = parser.parse_args()

    if args.command == "create-admin":
        asyncio.run(cmd_create_admin(args.email, args.password))
    elif args.command == "export-users":
        asyncio.run(cmd_export_users(args.output))
    elif args.command == "import-users":
        asyncio.run(cmd_import_users(args.input))


if __name__ == "__main__":
    main()
