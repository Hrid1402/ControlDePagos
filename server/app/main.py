from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as api_v1
from app.core.conexiones import detener_suscriptor, iniciar_suscriptor
from app.core.config import settings
from app.core.errores import registrar_manejadores


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
    # Cada proceso del server recibe por Redis los eventos de todos y entrega los de sus
    # conexiones WebSocket.
    suscriptor = await iniciar_suscriptor()
    yield
    await detener_suscriptor(suscriptor)


app = FastAPI(title="Control de Pagos", lifespan=ciclo_de_vida)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
registrar_manejadores(app)
app.include_router(api_v1, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "timezone": settings.timezone}
