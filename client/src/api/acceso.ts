import { esquemaUsuario, vencimiento } from '@/stores/sesion'
import type { CredencialesIngreso } from '@/types/acceso'
import type { PerfilCuenta, PoliticaPrivacidad, UsuarioCambiado } from '@/types/cuenta'
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

/** Valida la sesión que devuelve el servidor antes de reemplazar la actual. */
function sesionDe(data: unknown): SesionNueva {
  const respuesta = data as { usuario?: unknown; access_token?: unknown } | null
  const usuario = esquemaUsuario.safeParse(respuesta?.usuario)
  const token = respuesta?.access_token
  if (!usuario.success || typeof token !== 'string' || vencimiento(token) <= Date.now())
    throw respuestaInvalida()
  return { token, usuario: usuario.data }
}

export async function iniciarSesion(credenciales: CredencialesIngreso): Promise<SesionNueva> {
  const { data } = await http.post('/auth/login', credenciales)
  return sesionDe(data)
}

/** Devuelve el mensaje genérico del servidor: es el mismo exista o no la cuenta. */
export async function solicitarRecuperacion(username: string): Promise<string> {
  const { data } = await http.post('/auth/recuperar-contrasena', { username })
  return typeof data?.detail === 'string' ? data.detail : ''
}

export async function restablecerContrasena(token: string, nuevaContrasena: string): Promise<void> {
  await http.post('/auth/restablecer-contrasena', { token, nueva_contrasena: nuevaContrasena })
}

export async function obtenerPerfil(): Promise<PerfilCuenta> {
  const { data } = await http.get<PerfilCuenta>('/usuarios/perfil')
  return data
}

export async function actualizarPerfil(datos: Record<string, unknown>): Promise<PerfilCuenta> {
  const { data } = await http.put<PerfilCuenta>('/usuarios/perfil', datos)
  return data
}

export async function cambiarUsuario(username: string): Promise<UsuarioCambiado> {
  const { data } = await http.patch<UsuarioCambiado>('/me/usuario', { username })
  return data
}

/** Devuelve la sesión renovada: el token anterior queda revocado junto con las demás sesiones. */
export async function cambiarContrasena(
  contrasenaActual: string,
  contrasenaNueva: string,
): Promise<SesionNueva> {
  const { data } = await http.post('/me/contrasena', {
    contrasena_actual: contrasenaActual,
    contrasena_nueva: contrasenaNueva,
  })
  return sesionDe(data)
}

export async function obtenerPolitica(): Promise<PoliticaPrivacidad> {
  const { data } = await http.get<PoliticaPrivacidad>('/usuarios/politica')
  return data
}

export async function aceptarPolitica(version: string): Promise<PerfilCuenta> {
  const { data } = await http.post<PerfilCuenta>('/usuarios/politica', { version })
  return data
}
