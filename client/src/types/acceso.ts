export type PantallaAcceso =
  | 'ingreso'
  | 'recuperar'
  | 'correo-enviado'
  | 'restablecer'
  | 'clave-actualizada'
  | 'enlace-invalido'
  | 'sin-permiso'

export type EstadoIngreso =
  | 'normal'
  | 'vacio'
  | 'incorrecto'
  | 'bloqueado'
  | 'inactiva'
  | 'sin-conexion'
  | 'cargando'
  | 'vencida'
export interface CredencialesIngreso {
  username: string
  contrasena: string
}
