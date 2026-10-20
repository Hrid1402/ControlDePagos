import { http } from './http'
import type { CategoriaCalendario, DiaCalendario } from '@/components/calendario/modelo'

export interface FiltrosCalendario {
  desde: string
  hasta: string
  categoria: string
  estado: string
}

function parametros(filtros: FiltrosCalendario) {
  return {
    desde: filtros.desde,
    hasta: filtros.hasta,
    ...(filtros.categoria ? { categoria: filtros.categoria } : {}),
    ...(filtros.estado ? { estado: filtros.estado } : {}),
  }
}

export async function consultarCalendario(
  filtros: FiltrosCalendario,
  signal?: AbortSignal,
): Promise<DiaCalendario[]> {
  const { data } = await http.get<{ dias: DiaCalendario[] }>('/calendario', {
    params: parametros(filtros),
    signal,
  })
  return data.dias
}

export async function exportarCalendario(filtros: FiltrosCalendario): Promise<Blob> {
  const { data } = await http.get<Blob>('/calendario/exportar.ics', {
    params: parametros(filtros),
    responseType: 'blob',
  })
  return data
}

interface ServicioConCategoria {
  categoria: CategoriaCalendario
}

/** Incluye servicios de baja: sus deudas anteriores siguen visibles en el calendario. */
export async function listarCategoriasCalendario(): Promise<CategoriaCalendario[]> {
  const categorias = new Map<string, CategoriaCalendario>()
  let pagina = 1
  let total = 0
  do {
    const { data } = await http.get<{ items: ServicioConCategoria[]; total: number }>(
      '/servicios',
      {
        params: { estado: 'todos', page: pagina, size: 100 },
      },
    )
    total = data.total
    for (const servicio of data.items) categorias.set(servicio.categoria.id, servicio.categoria)
    if (!data.items.length) break
    pagina += 1
  } while ((pagina - 1) * 100 < total)
  return [...categorias.values()].sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'))
}
