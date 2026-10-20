import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  aprobarSolicitud,
  definirLimites,
  listarSolicitudes,
  rechazarSolicitud,
} from '@/api/limites'

const http = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }))
vi.mock('@/api/http', () => ({ http }))

const solicitudApi = {
  id: 's1',
  deuda_id: 'd1',
  asistente_id: 'a1',
  monto: '480.00',
  moneda: 'PEN',
  estado: 'aprobada',
  motivo: null,
  recordatorios_enviados: 0,
  resuelta_por: 'g1',
  resuelta_por_nombre: 'Carlos Mendoza',
  resuelta_en: '2026-10-20T16:00:00-05:00',
  creado_en: '2026-10-20T10:00:00-05:00',
  actualizado_en: '2026-10-20T16:00:00-05:00',
  servicio: 'Luz',
  asistente: 'Rosa Melgar',
  fecha_vencimiento: '2026-10-25',
}

beforeEach(() => {
  http.get.mockReset()
  http.put.mockReset()
  http.post.mockReset()
})

describe('cliente de límites y solicitudes', () => {
  it('un campo vacío viaja como sin límite y los montos no se convierten a número', async () => {
    http.put.mockResolvedValueOnce({ data: {} })
    await definirLimites({ por_pago: '  ', mensual: ' 1500.50 ' })
    expect(http.put).toHaveBeenCalledWith('/limites', { por_pago: null, mensual: '1500.50' })
  })

  it('lista por estado y nombra a quien resolvió', async () => {
    http.get.mockResolvedValueOnce({ data: { items: [solicitudApi], total: 1, page: 2 } })

    const { items, total } = await listarSolicitudes('aprobada', 2)

    expect(http.get).toHaveBeenCalledWith('/solicitudes', {
      params: { estado: 'aprobada', page: 2, size: 50 },
    })
    expect(total).toBe(1)
    expect(items[0]).toMatchObject({ resuelta_por: 'Carlos Mendoza', servicio: 'Luz' })
  })

  it('aprueba y rechaza con su motivo', async () => {
    http.post.mockResolvedValue({ data: solicitudApi })
    await aprobarSolicitud('s1')
    await rechazarSolicitud('s1', 'Este mes lo pago yo')
    expect(http.post).toHaveBeenNthCalledWith(1, '/solicitudes/s1/aprobar')
    expect(http.post).toHaveBeenNthCalledWith(2, '/solicitudes/s1/rechazar', {
      motivo: 'Este mes lo pago yo',
    })
  })
})
