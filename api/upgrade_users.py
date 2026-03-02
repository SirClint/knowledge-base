import asyncio
from db.database import async_session_maker
from sqlalchemy import text


async def main():
    async with async_session_maker() as s:
        await s.execute(text("UPDATE users SET role='admin'"))
        await s.commit()
        print("All users upgraded to admin")


asyncio.run(main())
