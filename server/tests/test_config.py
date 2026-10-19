import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app

cliente = TestClient(app)


def preflight(origen: str) -> dict[str, str]:
    r = cliente.options(
        "/health", headers={"Origin": origen, "Access-Control-Request-Method": "GET"}
    )
    return dict(r.headers)


def test_cors_acepta_el_origen_del_client() -> None:
    cabeceras = preflight("http://localhost:5173")
    assert cabeceras["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rechaza_otro_origen() -> None:
    assert "access-control-allow-origin" not in preflight("http://otro.com")


def test_la_configuracion_lee_cors_smtp_s3_y_redis_del_entorno(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variables = {
        "DATABASE_URL": "postgresql+psycopg://u:p@db:5432/x",
        "REDIS_URL": "redis://redis:6379/1",
        "JWT_SECRET": "clave-de-prueba-clave-de-prueba",
        "CORS_ORIGINS": '["https://pagos.example.com", "http://localhost:5173"]',
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_FROM": "avisos@example.com",
        "S3_ENDPOINT": "https://s3.example.com",
        "S3_REGION": "sa-east-1",
        "S3_BUCKET": "comprobantes",
        "S3_ACCESS_KEY": "acceso",
        "S3_SECRET_KEY": "secreto",
    }
    for nombre, valor in variables.items():
        monkeypatch.setenv(nombre, valor)

    config = Settings(_env_file=None)  # type: ignore[call-arg]

    assert config.cors_origins == ["https://pagos.example.com", "http://localhost:5173"]
    assert config.redis_url == "redis://redis:6379/1"
    assert (config.smtp_host, config.smtp_port, config.smtp_from) == (
        "smtp.example.com",
        587,
        "avisos@example.com",
    )
    assert config.s3_endpoint == "https://s3.example.com"
    assert config.s3_bucket == "comprobantes"
    assert config.s3_secret_key == "secreto"


def test_la_configuracion_exige_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("S3_BUCKET", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/1")
    monkeypatch.setenv("JWT_SECRET", "clave-de-prueba-clave-de-prueba")
    with pytest.raises(ValueError, match="s3_bucket"):
        Settings(_env_file=None)  # type: ignore[call-arg]
