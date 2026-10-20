import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  consultarCalendario,
  exportarCalendario,
  listarCategoriasCalendario,
} from '@/api/calendario'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/api/http', () => ({ http: { get } }))

beforeEach(() => get.mockReset())

describe('cliente del calendario', () => {
  it('envía rango y filtros y conserva las cifras decimales de la API', async () => {
    get.mockResolvedValueOnce({
      data: {
        dias: [
          {
            fecha: '2026-10-25',
            deudas: [],
            totales_confirmados: { PEN: '120.50', USD: '40.00' },
            totales_proyectados: {},
          },
        ],
      },
    })
    const filtros = {
      desde: '2026-10-01',
      hasta: '2026-10-31',
      categoria: 'cat-1',
      estado: 'pendiente',
    }
    const dias = await consultarCalendario(filtros)
    expect(get).toHaveBeenCalledWith('/calendario', { params: filtros, signal: undefined })
    expect(dias[0]?.totales_confirmados).toEqual({ PEN: '120.50', USD: '40.00' })
  })

  it('exporta el mismo rango filtrado como blob', async () => {
    const archivo = new Blob(['BEGIN:VCALENDAR'])
    get.mockResolvedValueOnce({ data: archivo })
    const filtros = { desde: '2026-10-01', hasta: '2026-10-31', categoria: '', estado: '' }
    expect(await exportarCalendario(filtros)).toBe(archivo)
    expect(get).toHaveBeenCalledWith('/calendario/exportar.ics', {
      params: { desde: filtros.desde, hasta: filtros.hasta },
      responseType: 'blob',
    })
  })

  it('reúne categorías de servicios activos y de baja a través de páginas', async () => {
    get.mockResolvedValueOnce({
      data: { items: [{ categoria: { id: 'b', nombre: 'Luz' } }], total: 101 },
    })
    get.mockResolvedValueOnce({
      data: { items: [{ categoria: { id: 'a', nombre: 'Agua' } }], total: 101 },
    })
    expect(await listarCategoriasCalendario()).toEqual([
      { id: 'a', nombre: 'Agua' },
      { id: 'b', nombre: 'Luz' },
    ])
    expect(get).toHaveBeenNthCalledWith(2, '/servicios', {
      params: { estado: 'todos', page: 2, size: 100 },
    })
  })
})
