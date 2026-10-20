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
}
