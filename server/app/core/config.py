from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_expires_minutes: int = 30
    login_intentos_maximos: int = 5
    login_minutos_bloqueo: int = 15
    timezone: str = "America/Lima"
    cors_origins: list[str] = ["http://localhost:5173"]
    url_cliente: str = "http://localhost:5173"

    smtp_host: str
    smtp_port: int
    smtp_from: str
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_tls: bool = False

    s3_endpoint: str
    s3_region: str
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: str

    # El worker de la cola ocr carga el modelo al iniciar cada proceso (pnpm worker:ocr lo activa).
    ocr_precargar: bool = False

    # Responsable que informa la política de privacidad (app/core/politica.py). Cada instalación
    # debe configurar su domicilio y su correo de contacto antes de producción.
    politica_responsable: str = "Deconsta"
    politica_domicilio: str | None = None
    politica_correo: str | None = None


settings = Settings()  # type: ignore[call-arg]
