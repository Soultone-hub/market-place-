import os
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from .domain import SYSTEM_ACTOR_ID, Role
from .persistence.postgres_models import ActorRecord, Base

DEMO_ACTORS = {
    "buyer-1": Role.BUYER,
    "seller-1": Role.SELLER,
    "courier-1": Role.COURIER,
    "courier-2": Role.COURIER,
    SYSTEM_ACTOR_ID: Role.SYSTEM,
}


def make_sessions(database_url: str) -> sessionmaker:
    url = make_url(database_url)
    if url.database is not None:
        url = url.set(database=unquote(url.database))
    engine = create_engine(
        url,
        isolation_level="READ COMMITTED",
        connect_args={"options": "-c timezone=UTC"},
    )
    return sessionmaker(engine, expire_on_commit=False)


def configured_sessions() -> sessionmaker:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Set DATABASE_URL in the project's .env file or environment.")
    return make_sessions(database_url)


def initialize(sessions: sessionmaker) -> None:
    with sessions.begin() as session:
        Base.metadata.create_all(session.connection())
        session.execute(
            insert(ActorRecord)
            .values([{"id": actor_id, "role": role} for actor_id, role in DEMO_ACTORS.items()])
            .on_conflict_do_nothing(index_elements=[ActorRecord.id])
        )


if __name__ == "__main__":
    initialize(configured_sessions())
