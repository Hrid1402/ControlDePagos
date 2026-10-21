"""Comentarios de una deuda (H17 CA06, TASK-54).

Errores: 404 NO_ENCONTRADO (deuda inexistente o de otro gerente), 422 VALIDACION (texto vacío o de
más de 500 caracteres) y 409 ESTADO_NO_PERMITIDO (deuda anulada).
"""

import uuid

from fastapi import APIRouter, status

from app.core.dependencias import SesionDb, UsuarioActual
from app.schemas.comentarios import ComentarioEntrada, ComentarioSalida
from app.services.auditoria import nombre_de
from app.services.comentarios import FilaComentario, comentar, listar_comentarios

router = APIRouter(prefix="/deudas", tags=["comentarios"])


def salida(fila: FilaComentario, usuario_id: uuid.UUID) -> ComentarioSalida:
    return ComentarioSalida(
        id=fila.comentario.id,
        texto=fila.comentario.texto,
        autor=nombre_de(fila.autor),
        rol=fila.autor.rol,
        propio=fila.autor.id == usuario_id,
        creado_en=fila.comentario.creado_en,
    )


@router.get("/{deuda_id}/comentarios")
def listar(deuda_id: uuid.UUID, db: SesionDb, usuario: UsuarioActual) -> list[ComentarioSalida]:
    return [salida(f, usuario.id) for f in listar_comentarios(db, usuario, deuda_id)]


@router.post("/{deuda_id}/comentarios", status_code=status.HTTP_201_CREATED)
def crear(
    deuda_id: uuid.UUID, entrada: ComentarioEntrada, db: SesionDb, usuario: UsuarioActual
) -> ComentarioSalida:
    fila = comentar(db, usuario, deuda_id, entrada.texto)
    db.commit()
    return salida(fila, usuario.id)
