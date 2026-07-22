from __future__ import annotations

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./randomization.db")
_IS_SQLITE = DATABASE_URL.startswith("sqlite")


class Base(DeclarativeBase):
    pass


# check_same_thread=False：允許 FastAPI 線程池多請求共用引擎
# timeout：SQLite 鎖等待秒數，避免多人同時改記錄時立刻 database is locked
_connect_args: dict = {}
if _IS_SQLITE:
    _connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)


if _IS_SQLITE:

    @event.listens_for(engine, "connect")
    def _sqlite_on_connect(dbapi_connection, connection_record) -> None:  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        # WAL：讀寫可並行，適合多人同時打開管理台改記錄列表
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
