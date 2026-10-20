import { http } from './http'
import type {
  ConsumoMes,
  EstadoSolicitud,
  Limites,
  Moneda,
  Solicitud,
} from '@/components/limites/modelo'

// Límites y solicitudes de aprobación del gerente (H05). Los montos viajan como texto con dos
// decimales: nunca se convierten a número para no perder centavos.

export interface LimitesConsumo extends Limites {
  consumo: ConsumoMes
  mes: string
}

export async function obtenerLimites(): Promise<LimitesConsumo> {
  const { data } = await http.get<LimitesConsumo>('/limites')
  return data
}

/** Un campo vacío es sin límite (CA03). */
export async function definirLimites(valores: {
  por_pago?: unknown
  mensual?: unknown
}): Promise<LimitesConsumo> {
  const monto = (valor: unknown) =>
    String(valor ?? '').trim() === '' ? null : String(valor).trim()
  const { data } = await http.put<LimitesConsumo>('/limites', {
    por_pago: monto(valores.por_pago),
    mensual: monto(valores.mensual),
  })
  return data
}

interface SolicitudApi {
  id: string
  monto: string
  moneda: Moneda
  estado: EstadoSolicitud
  motivo: string | null
  servicio: string
  asistente: string
  fecha_vencimiento: string
  creado_en: string
  resuelta_en: string | null
  resuelta_por_nombre: string | null
}

const solicitud = (s: SolicitudApi): Solicitud => ({
  id: s.id,
  servicio: s.servicio,
  asistente: s.asistente,
  monto: s.monto,
  moneda: s.moneda,
  estado: s.estado,
  fecha_vencimiento: s.fecha_vencimiento,
  creado_en: s.creado_en,
  motivo: s.motivo,
  resuelta_por: s.resuelta_por_nombre,
  resuelta_en: s.resuelta_en,
})

export const TAMANO_SOLICITUDES = 50

export async function listarSolicitudes(
  estado: EstadoSolicitud,
  pagina = 1,
): Promise<{ items: Solicitud[]; total: number }> {
  const { data } = await http.get<{ items: SolicitudApi[]; total: number }>('/solicitudes', {
    params: { estado, page: pagina, size: TAMANO_SOLICITUDES },
  })
  return { items: data.items.map(solicitud), total: data.total }
}

export async function aprobarSolicitud(id: string): Promise<Solicitud> {
  const { data } = await http.post<SolicitudApi>(`/solicitudes/${id}/aprobar`)
  return solicitud(data)
}

export async function rechazarSolicitud(id: string, motivo: string | null): Promise<Solicitud> {
  const { data } = await http.post<SolicitudApi>(`/solicitudes/${id}/rechazar`, { motivo })
  return solicitud(data)
}
