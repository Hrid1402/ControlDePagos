from fastapi import FastAPI

from app.core.config import settings
from app.core.errores import registrar_manejadores

app = FastAPI(title="Control de Pagos")
registrar_manejadores(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "timezone": settings.timezone}
