from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    output_dir: str = "/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/Downloads"
    timezone: str = "Europe/Istanbul"
    broker: str = "IBKR"
    default_account: str = "UXXXXXXX"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()  # singleton
