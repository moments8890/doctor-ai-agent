import db.models  # noqa: F401 — ensure models are registered before create_all
from db.engine import Base, engine


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
