import { http } from './http'
import type { Contadores, ItemBandeja, Pestana } from '@/components/bandeja/modelo'

// Bandeja de la asistente (H15): deudas por prioridad, contadores, fijar y recordar mañana.

export interface PaginaBandeja {
  items: ItemBandeja[]
  total: number
  page: number
  contadores: Contadores
}

export interface ConsultaBandeja {
  pestana: Pestana
  categoria: string
}

/** Una página de la pestaña; sin categoría trae todas. */
export async function obtenerBandeja(
  consulta: ConsultaBandeja,
  page: number,
  signal?: AbortSignal,
): Promise<PaginaBandeja> {
  const { data } = await http.get<PaginaBandeja>('/bandeja', {
    params: {
      pestana: consulta.pestana,
      categoria: consulta.categoria || undefined,
      page,
      size: 100,
    },
    signal,
  })
  return data
}

/** La bandeja completa de la pestaña: casi siempre cabe en una página. */
export async function obtenerBandejaCompleta(
  consulta: ConsultaBandeja,
  signal?: AbortSignal,
): Promise<PaginaBandeja> {
  const primera = await obtenerBandeja(consulta, 1, signal)
  const items = [...primera.items]
  for (let page = 2; items.length < primera.total; page++) {
    const siguiente = await obtenerBandeja(consulta, page, signal)
    if (!siguiente.items.length) break
    items.push(...siguiente.items)
  }
  return { ...primera, items }
}

export interface PrioridadDeuda {
  id: string
  fijada: boolean
  oculta_hasta: string | null
}

/** CA07: valor explícito, así repetir la solicitud no deshace el cambio. */
export async function fijarDeuda(id: string, fijada: boolean): Promise<PrioridadDeuda> {
  const { data } = await http.post<PrioridadDeuda>(`/deudas/${id}/fijar`, { fijada })
  return data
}

/** CA08: la oculta hasta las 08:00 del día siguiente en Lima. */
export async function recordarManana(id: string): Promise<PrioridadDeuda> {
  const { data } = await http.post<PrioridadDeuda>(`/deudas/${id}/recordar-manana`)
  return data
}
