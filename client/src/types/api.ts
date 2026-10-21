export type Rol = 'gerente' | 'asistente'

export interface UsuarioSesion {
  id: string
  rol: Rol
  nombre: string
}

export interface ErrorApi {
  status: number
  code: string
  detail: string
  field: string | null
  /** Claves adicionales del error, como deuda_existente en un 409 DUPLICADO. */
  datos?: Record<string, unknown>
}
