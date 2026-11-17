from collections.abc import Iterator

import pytest
from sqlalchemy.exc import OperationalError

from app.storage.config import MySQLSettings
from app.storage.database import Database


@pytest.fixture(scope="session")
def mysql_database() -> Iterator[Database]:
    settings = MySQLSettings().model_copy(
        update={"name": "miniharness_test"},
    )
    database = Database(settings)
    try:
        database.ping()
    except OperationalError as exc:
        pytest.skip(f"MySQL test database is unavailable: {exc}")

    database.drop_schema_for_tests()
    database.create_schema()
    yield database
    database.drop_schema_for_tests()
    database.dispose()


@pytest.fixture()
def empty_mysql_database(mysql_database: Database) -> Database:
    mysql_database.drop_schema_for_tests()
    mysql_database.create_schema()
    return mysql_database
