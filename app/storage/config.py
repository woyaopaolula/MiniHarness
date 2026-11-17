from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MySQLSettings(BaseSettings):
    """从环境变量或本地 .env 读取 MySQL 连接配置。"""

    model_config = SettingsConfigDict(
        env_prefix="MINIHARNESS_DB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = Field(default=3307, ge=1, le=65535)
    user: str
    password: SecretStr
    name: str
