import {
  nombreDe,
  type AsistenteDetalle,
  type AsistenteFila,
  type Credenciales,
  type Disponibilidad,
  type ResultadoActivacion,
  type ResultadoDesactivacion,
} from '@/types/asistentes'
import { http } from './http'

// Gestión de asistentes del gerente (H03). Las contraseñas que devuelven crear y restablecer no
// se guardan en ningún lado: viven solo en la pantalla que las muestra.

/** Un gerente tiene pocas cuentas: se piden todas en una sola página. */
export async function listarAsistentes(): Promise<AsistenteFila[]> {
  const { data } = await http.get<{ items: AsistenteFila[] }>('/asistentes', {
    params: { size: 100 },
  })
  return data.items
}

export async function obtenerAsistente(id: string): Promise<AsistenteDetalle> {
  const { data } = await http.get<AsistenteDetalle>(`/asistentes/${id}`)
  return data
}

export async function consultarDisponibilidad(
  username: string,
  signal?: AbortSignal,
): Promise<Disponibilidad> {
  const { data } = await http.get<Disponibilidad>('/asistentes/disponibilidad', {
    params: { username },
    signal,
  })
  return data
}

export async function crearAsistente(datos: {
  nombres: string
  apellidos: string
  username?: string
  contrasena?: string
  activar_ahora: boolean
}): Promise<Credenciales & { estado: AsistenteFila['estado'] }> {
  const { data } = await http.post('/asistentes', datos)
  return {
    id: data.id,
    nombre: nombreDe(data),
    username: data.username,
    contrasena: data.contrasena,
    estado: data.estado,
  }
}

export async function activarAsistente(id: string): Promise<ResultadoActivacion> {
  const { data } = await http.post<ResultadoActivacion>(`/asistentes/${id}/activar`)
  return data
}

export async function desactivarAsistente(id: string): Promise<ResultadoDesactivacion> {
  const { data } = await http.post<ResultadoDesactivacion>(`/asistentes/${id}/desactivar`)
  return data
}

export async function eliminarAsistente(id: string): Promise<void> {
  await http.delete(`/asistentes/${id}`)
}

export async function restablecerContrasena(
  cuenta: Pick<AsistenteFila, 'id' | 'nombres' | 'apellidos' | 'username'>,
): Promise<Credenciales> {
  const { data } = await http.post(`/asistentes/${cuenta.id}/restablecer-contrasena`)
  return {
    id: data.id,
    nombre: nombreDe(cuenta),
    username: data.username,
    contrasena: data.contrasena,
  }
}
