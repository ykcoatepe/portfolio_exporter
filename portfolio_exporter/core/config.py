try:
    from pydantic import BaseModel  # type: ignore
except Exception:  # lightweight fallback
    class BaseModel:  # type: ignore
        pass

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore
except Exception:  # lightweight fallback for test environments without deps
    class BaseSettings:  # type: ignore
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    def SettingsConfigDict(**_kwargs):  # type: ignore
        return {}


class GreeksSettings(BaseModel):
    risk_free: float = 0.03


class Settings(BaseSettings):
    # Default to iCloud Drive Downloads path used on the target machine.
    # Callers can still override via OUTPUT_DIR/PE_OUTPUT_DIR or .env; writers
    # will smartly fall back to a local path if this location is not writable.
    output_dir: str = "/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/Downloads"
    timezone: str = "Europe/Istanbul"
    broker: str = "IBKR"
    default_account: str = "UXXXXXXX"
    greeks: GreeksSettings = GreeksSettings()
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()  # singleton
