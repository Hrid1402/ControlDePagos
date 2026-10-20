import { esquemaUsuario, vencimiento } from '@/stores/sesion'
import type { CredencialesIngreso } from '@/types/acceso'
import type { ErrorApi, UsuarioSesion } from '@/types/api'
import { http } from './http'

export interface SesionNueva {
  token: string
  usuario: UsuarioSesion
}

function respuestaInvalida(): ErrorApi {
  return {
    status: 0,
    code: 'RESPUESTA_INVALIDA',
    detail: 'No pudimos abrir tu sesión. Intenta de nuevo.',
    field: null,
  }
}

export async function iniciarSesion(credenciales: CredencialesIngreso): Promise<SesionNueva> {
  const { data } = await http.post('/auth/login', credenciales)
  const usuario = esquemaUsuario.safeParse(data?.usuario)
  const token: unknown = data?.access_token
  if (!usuario.success || typeof token !== 'string' || vencimiento(token) <= Date.now())
    throw respuestaInvalida()
  return { token, usuario: usuario.data }
}

/** Devuelve el mensaje genérico del servidor: es el mismo exista o no la cuenta. */
export async function solicitarRecuperacion(username: string): Promise<string> {
  const { data } = await http.post('/auth/recuperar-contrasena', { username })
  return typeof data?.detail === 'string' ? data.detail : ''
}

export async function restablecerContrasena(token: string, nuevaContrasena: string): Promise<void> {
  await http.post('/auth/restablecer-contrasena', { token, nueva_contrasena: nuevaContrasena })
}
