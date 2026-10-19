from fastapi import APIRouter

# Router de la API v1, montado en /api/v1. Cada módulo define su propio router en
# app/api/v1/<modulo>.py y se registra aquí con router.include_router(<modulo>.router).
router = APIRouter()
