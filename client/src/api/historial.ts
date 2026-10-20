import { http } from './http'
import type { FiltrosHistorial, PaginaHistorial } from '@/components/historial/modelo'

// Historial de acciones del gerente (H34). El listado y el Excel usan los mismos filtros.

export const TAMANO_PAGINA = 30

function parametros(filtros: FiltrosHistorial) {
  return Object.fromEntries(Object.entries(filtros).filter(([, valor]) => valor))
}

export async function listarHistorial(
  filtros: FiltrosHistorial,
  pagina: number,
  signal?: AbortSignal,
): Promise<PaginaHistorial> {
  const { data } = await http.get<PaginaHistorial>('/auditoria', {
    params: { ...parametros(filtros), page: pagina, size: TAMANO_PAGINA },
    signal,
  })
  return data
}

export async function exportarHistorial(filtros: FiltrosHistorial): Promise<Blob> {
  const { data } = await http.get<Blob>('/auditoria/exportar', {
    params: parametros(filtros),
    responseType: 'blob',
  })
  return data
}
