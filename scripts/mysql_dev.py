import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.config import MySQLSettings  # noqa: E402

MYSQL_ROOT = Path(sys.prefix) / "Library"
MYSQL_EXE = MYSQL_ROOT / "bin" / "mysqld.exe"
DATA_DIR = PROJECT_ROOT / "data" / "mysql"
LOG_DIR = PROJECT_ROOT / "logs"
PID_FILE = DATA_DIR / "mysqld.pid"
ERROR_LOG = LOG_DIR / "mysql-error.log"
MESSAGES_DIR = MYSQL_ROOT / "share" / "mysql"


def connect(
    settings: MySQLSettings,
    *,
    password: str | None = None,
    database: str | None = None,
) -> pymysql.Connection:
    return pymysql.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=(
            settings.password.get_secret_value()
            if password is None
            else password
        ),
        database=database,
        connect_timeout=2,
        autocommit=True,
    )


def server_version(settings: MySQLSettings) -> str | None:
    try:
        connection = connect(settings)
    except pymysql.MySQLError:
        return None
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            row = cursor.fetchone()
            return str(row[0]) if row else None
    finally:
        connection.close()


def initialize() -> None:
    if not MYSQL_EXE.exists():
        raise RuntimeError(f"mysqld not found: {MYSQL_EXE}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if any(DATA_DIR.iterdir()):
        raise RuntimeError(f"Refusing to initialize non-empty directory: {DATA_DIR}")

    result = subprocess.run(
        [
            str(MYSQL_EXE),
            "--initialize-insecure",
            f"--basedir={MYSQL_ROOT}",
            f"--datadir={DATA_DIR}",
            f"--lc-messages-dir={MESSAGES_DIR}",
            "--console",
        ],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"MySQL initialization failed: {result.returncode}")


def wait_until_ready(settings: MySQLSettings, seconds: int = 30) -> str:
    for _ in range(seconds * 2):
        version = server_version(settings)
        if version is not None:
            return version
        time.sleep(0.5)
    raise RuntimeError(f"MySQL did not become ready; inspect {ERROR_LOG}")


def provision(settings: MySQLSettings) -> None:
    password = settings.password.get_secret_value()
    test_database = f"{settings.name}_test"
    statements = [
        (
            f"CREATE DATABASE IF NOT EXISTS `{settings.name}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
        ),
        (
            f"CREATE DATABASE IF NOT EXISTS `{test_database}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
        ),
        (
            f"CREATE USER IF NOT EXISTS '{settings.user}'@'127.0.0.1' "
            "IDENTIFIED BY %s"
        ),
        (
            f"ALTER USER '{settings.user}'@'127.0.0.1' "
            "IDENTIFIED BY %s"
        ),
        (
            f"GRANT ALL PRIVILEGES ON `{settings.name}`.* "
            f"TO '{settings.user}'@'127.0.0.1'"
        ),
        (
            f"GRANT ALL PRIVILEGES ON `{test_database}`.* "
            f"TO '{settings.user}'@'127.0.0.1'"
        ),
        "FLUSH PRIVILEGES",
    ]

    connection = pymysql.connect(
        host=settings.host,
        port=settings.port,
        user="root",
        password="",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                if "%s" in statement:
                    cursor.execute(statement, (password,))
                else:
                    cursor.execute(statement)
    finally:
        connection.close()


def start() -> None:
    settings = MySQLSettings()
    version = server_version(settings)
    if version is not None:
        provision(settings)
        print(f"MySQL is already running: {version} on port {settings.port}")
        return

    if not DATA_DIR.exists() or not any(DATA_DIR.iterdir()):
        initialize()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    process_options = {}
    if os.name == "nt":
        process_options["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )

    subprocess.Popen(
        [
            str(MYSQL_EXE),
            f"--basedir={MYSQL_ROOT}",
            f"--datadir={DATA_DIR}",
            f"--port={settings.port}",
            "--bind-address=127.0.0.1",
            "--mysqlx=0",
            f"--pid-file={PID_FILE}",
            f"--log-error={ERROR_LOG}",
            f"--lc-messages-dir={MESSAGES_DIR}",
            "--character-set-server=utf8mb4",
            "--collation-server=utf8mb4_0900_ai_ci",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        **process_options,
    )
    version = wait_until_ready(settings)
    provision(settings)
    print(f"MySQL started: {version} on port {settings.port}")


def stop() -> None:
    settings = MySQLSettings()
    if server_version(settings) is None:
        print("MySQL is not running")
        return

    try:
        connection = pymysql.connect(
            host=settings.host,
            port=settings.port,
            user="root",
            password="",
            autocommit=True,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute("SHUTDOWN")
        finally:
            connection.close()
    except pymysql.MySQLError:
        if not PID_FILE.exists():
            raise
        os.kill(int(PID_FILE.read_text(encoding="utf-8").strip()), signal.SIGTERM)

    for _ in range(40):
        if server_version(settings) is None:
            print("MySQL stopped")
            return
        time.sleep(0.25)
    raise RuntimeError("MySQL did not stop within 10 seconds")


def status() -> None:
    settings = MySQLSettings()
    version = server_version(settings)
    if version is None:
        print(f"MySQL is not running on {settings.host}:{settings.port}")
        return
    print(f"MySQL {version} is running on {settings.host}:{settings.port}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage local MiniHarness MySQL")
    parser.add_argument("command", choices=["start", "stop", "status"])
    args = parser.parse_args()

    if args.command == "start":
        start()
    elif args.command == "stop":
        stop()
    else:
        status()


if __name__ == "__main__":
    main()
