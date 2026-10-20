from fastapi import APIRouter

from app.api.v1 import (
    asistentes,
    auditoria,
    auth,
    bandeja,
    calendario,
    categorias,
    deudas,
    empresas,
    limites,
    me,
    ordenes,
    pagos,
    servicios,
    solicitudes,
    tiempo_real,
    usuarios,
)

# Router de la API v1, montado en /api/v1. Cada módulo define su propio router en
# app/api/v1/<modulo>.py y se registra aquí con router.include_router(<modulo>.router).
router = APIRouter()
router.include_router(asistentes.router)
router.include_router(auditoria.router)
router.include_router(auth.router)
router.include_router(bandeja.router)
router.include_router(calendario.router)
router.include_router(categorias.router)
router.include_router(deudas.router)
router.include_router(empresas.router)
router.include_router(limites.router)
router.include_router(me.router)
router.include_router(ordenes.router)
router.include_router(pagos.router)
router.include_router(servicios.router)
router.include_router(solicitudes.router)
router.include_router(tiempo_real.router)
router.include_router(usuarios.router)
