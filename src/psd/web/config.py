from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    test_mode: bool = Field(False, alias="SSE_TEST_MODE")
    disable_background: bool = False
    msb_startup_refresh: bool = Field(True, alias="MSB_STARTUP_REFRESH")
    sse_heartbeat_sec: int = Field(15, alias="SSE_HEARTBEAT_SEC")

    model_config = SettingsConfigDict(
        env_prefix="PSD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
