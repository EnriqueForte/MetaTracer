"""Inspect the local SQLite user table (never prints the hash itself)."""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///./data/metatracer.db")
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT username, role, length(password_hash), "
                    "substr(password_hash, 1, 13) FROM \"user\""
                )
            )
        ).fetchall()
        print("users:", [(r[0], r[1], r[2], r[3]) for r in rows])
        sessions = (await conn.execute(text("SELECT COUNT(*) FROM user_session"))).fetchone()
        print("active session rows:", sessions[0])
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
