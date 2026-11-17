from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.storage.config import MySQLSettings
from app.storage.models import Base


class Database:
    """管理 MySQL 引擎、连接池和 Session 生命周期。"""

    def __init__(self, settings: MySQLSettings | None = None) -> None:
        self.settings = settings or MySQLSettings()
        url = URL.create(
            drivername="mysql+pymysql",
            username=self.settings.user,
            password=self.settings.password.get_secret_value(),
            host=self.settings.host,
            port=self.settings.port,
            database=self.settings.name,
            query={"charset": "utf8mb4"},
        )
        self.engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        self._session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False,
        )

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def drop_schema_for_tests(self) -> None:
        if not self.settings.name.endswith("_test"):
            raise RuntimeError("Refusing to drop a non-test database schema")
        Base.metadata.drop_all(self.engine)

    def ping(self) -> None:
        with self.engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()
