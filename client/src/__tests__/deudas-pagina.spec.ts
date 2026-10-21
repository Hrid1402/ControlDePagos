import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import { configuracionUi } from '@/config/ui'
import DeudasPage from '@/pages/DeudasPage.vue'
import * as api from '@/api/deudas'
import { useSesionStore } from '@/stores/sesion'
import { FILTROS_INICIALES } from '@/components/deudas/listado'

vi.mock('@/api/deudas', () => ({ listarDeudas: vi.fn(), registrarDeuda: vi.fn() }))
vi.mock('@/api/categorias', () => ({ listarCategorias: vi.fn().mockResolvedValue([]) }))
vi.mock('@/api/servicios', () => ({ listarServicios: vi.fn() }))
const simulada = vi.mocked(api)

const vacio = {
  cantidad: 0,
  monto: '0',
  pagado: '0',
  saldo: '0',
  sin_monto: 0,
  proyectado: '0',
  sin_estimacion: 0,
}
const montados: VueWrapper[] = []
beforeEach(() => {
  setActivePinia(createPinia())
  simulada.listarDeudas.mockReset()
  useSesionStore().usuario = { id: 'u1', rol: 'gerente', nombre: 'Carlos' }
  simulada.listarDeudas.mockResolvedValue({
    items: [
      {
        id: 'd1',
        servicio_id: 's1',
        empresa: 'Hidrandina',
        alias: null,
        codigo_suministro: '123',
        categoria: { id: 'c1', nombre: 'Luz', color: '#F59E0B', icono: 'pi-bolt', tipo: 'x' },
        periodo: '2026-10',
        monto: '85.40',
        moneda: 'PEN',
        pagado: '0.00',
        saldo: '85.40',
        monto_proyectado: null,
        fecha_vencimiento: '2026-10-25',
        vencida: false,
        estado: 'pendiente',
        numero_recibo: null,
      },
    ],
    total: 1,
    page: 1,
    totales: { PEN: { ...vacio, cantidad: 1, monto: '85.40', saldo: '85.40' }, USD: vacio },
  })
})
afterEach(() => montados.splice(0).forEach((w) => w.unmount()))

async function montar(ruta: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/gerente/deudas', component: DeudasPage },
      { path: '/gerente/deudas/:id', name: 'gerente-deuda', component: { render: () => null } },
    ],
  })
  await router.push(ruta)
  const vista = mount(defineComponent({ setup: () => () => h(RouterView) }), {
    global: { plugins: [router, [PrimeVue, configuracionUi], ToastService] },
  })
  montados.push(vista)
  await flushPromises()
  return { vista, router }
}

describe('pantalla de deudas (H36)', () => {
  it('lee los filtros de la URL y los actualiza al filtrar (CA09, CA13)', async () => {
    const { vista, router } = await montar('/gerente/deudas?vista=vencidas&mes=2026-10&page=2')

    expect(simulada.listarDeudas).toHaveBeenCalledWith(
      { ...FILTROS_INICIALES, vista: 'vencidas', mes: '2026-10', page: 2 },
      expect.any(AbortSignal),
    )
    await vista.get('.vistas button').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ mes: '2026-10' })
    expect(simulada.listarDeudas).toHaveBeenCalledTimes(2)
  })

  it('al tocar una deuda abre su detalle (CA07)', async () => {
    const { vista, router } = await montar('/gerente/deudas')

    await vista.get('tbody tr').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe('/gerente/deudas/d1')
  })
})
