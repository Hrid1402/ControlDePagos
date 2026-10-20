import { http } from './http'
import type {
  DatosServicio,
  Empresa,
  FiltroEstado,
  Servicio,
  ServicioDetalle,
} from '@/components/servicios/modelo'

// Servicios del gerente (H10). Gerente y asistente listan, registran y editan; la baja y la
// reactivación son solo del gerente (CA08).

export const TAMANO_PAGINA = 30

export interface FiltrosServicios {
  q: string
  categoria_id: string
  estado: FiltroEstado
}

export interface PaginaServicios {
  items: Servicio[]
  total: number
  page: number
}

export interface ServicioEditado extends Servicio {
  advertencias: { codigo_cambiado: boolean; deudas_pendientes: number }
}

export async function listarServicios(
  filtros: FiltrosServicios,
  pagina: number,
  signal?: AbortSignal,
): Promise<PaginaServicios> {
  const params = Object.fromEntries(Object.entries(filtros).filter(([, valor]) => valor))
  const { data } = await http.get<PaginaServicios>('/servicios', {
    params: { ...params, page: pagina, size: TAMANO_PAGINA },
    signal,
  })
  return data
}

/** Trae las deudas pendientes: el formulario advierte con ellas al cambiar el código (CA07). */
export async function obtenerServicio(id: string): Promise<ServicioDetalle> {
  const { data } = await http.get<ServicioDetalle>(`/servicios/${id}`)
  return data
}

export async function listarEmpresas(): Promise<Empresa[]> {
  const { data } = await http.get<Empresa[]>('/empresas')
  return data
}

export async function crearServicio(datos: DatosServicio): Promise<Servicio> {
  const { data } = await http.post<Servicio>('/servicios', datos)
  return data
}

export async function editarServicio(id: string, datos: DatosServicio): Promise<ServicioEditado> {
  const { data } = await http.put<ServicioEditado>(`/servicios/${id}`, datos)
  return data
}

export async function darDeBajaServicio(id: string): Promise<Servicio> {
  const { data } = await http.post<Servicio>(`/servicios/${id}/baja`)
  return data
}

export async function reactivarServicio(id: string): Promise<Servicio> {
  const { data } = await http.post<Servicio>(`/servicios/${id}/reactivar`)
  return data
}
