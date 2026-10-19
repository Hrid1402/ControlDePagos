from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(title="Control de Pagos")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "timezone": settings.timezone}
