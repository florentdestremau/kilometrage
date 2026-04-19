from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    graphhopper_api_key: str = ""
    anthropic_api_key: str = ""
    toll_rate_eur_per_km: float = 0.10
    storage_dir: str = "/storage"
    cache_max_size: int = 100  # max entrées en mémoire pour le cache requêtes


settings = Settings()
