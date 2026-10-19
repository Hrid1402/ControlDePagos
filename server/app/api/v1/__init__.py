from fastapi import APIRouter

from app.api.v1 import auth, tiempo_real

# Router de la API v1, montado en /api/v1. Cada módulo define su propio router en
# app/api/v1/<modulo>.py y se registra aquí con router.include_router(<modulo>.router).
router = APIRouter()
router.include_router(auth.router)
router.include_router(tiempo_real.router)
