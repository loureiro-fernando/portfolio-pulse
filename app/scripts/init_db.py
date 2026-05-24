import asyncio

from app.db import engine
from app.models import entities  # noqa: F401 - registers models with metadata
from app.models.base import Base


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("DB initialized")


if __name__ == "__main__":
    asyncio.run(main())
