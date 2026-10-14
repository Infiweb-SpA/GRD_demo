from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración central del Sistema GRD Comunal.

    Cada valor puede sobrescribirse con una variable de entorno
    o mediante un archivo .env en la raíz del proyecto.
    """

    APP_NAME: str = "Sistema GRD Comunal"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"  # development | production

    # Seguridad: en producción SIEMPRE define SECRET_KEY por variable de entorno
    SECRET_KEY: str = "cambiar-esta-clave-en-produccion"
    SESSION_COOKIE_NAME: str = "grd_session"
    SESSION_MAX_AGE: int = 60 * 60 * 8  # 8 horas

    # Base de datos (SQLite local; SpatiaLite se integra en el Módulo 2)
    DATABASE_URL: str = "sqlite:///./grd.db"

    # Credenciales del superadmin creado en el primer arranque
    SUPERADMIN_USERNAME: str = "superadmin"
    SUPERADMIN_PASSWORD: str = "Admin@1234"

    # Servicios externos
    OPEN_METEO_URL: str = "https://api.open-meteo.com/v1/forecast"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()