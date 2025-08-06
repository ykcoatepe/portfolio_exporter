from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class GreeksSettings(BaseModel):
    risk_free: float = 0.03


class Settings(BaseSettings):
    output_dir: str = (
        "/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/Downloads"
    )
    timezone: str = "Europe/Istanbul"
    broker: str = "IBKR"
    default_account: str = "UXXXXXXX"
    greeks: GreeksSettings = GreeksSettings()
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()  # singleton
