import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import { configuracionUi } from '@/config/ui'
import DeudaDetallePage from '@/pages/DeudaDetallePage.vue'
import * as api from '@/api/deudas'
import { useSesionStore } from '@/stores/sesion'
import type { DetalleDeuda } from '@/components/deudas/detalle'

vi.mock('@/api/deudas', () => ({
  obtenerDeuda: vi.fn(),
  listarComentarios: vi.fn(),
  comentarDeuda: vi.fn(),
  iniciarPago: vi.fn(),
  cancelarInicio: vi.fn(),
}))
vi.mock('@/api/comprobantes', () => ({ subirComprobante: vi.fn(), obtenerComprobante: vi.fn() }))
const simulada = vi.mocked(api)

const detalle = {
  id: 'd1',
  servicio: {
    id: 's1',
    empresa: 'Hidrandina',
    alias: null,
    codigo_suministro: '123',
    titular: null,
    lugar_pago: null,
    notas: null,
  },
  categoria: { id: 'c1', nombre: 'Luz', color: '#F59E0B', icono: 'pi-bolt', tipo: 'x' },
  periodo: '2026-10',
  estado: 'pendiente',
  origen: 'manual',
  moneda: 'PEN',
  monto: '85.40',
  pagado: '0.00',
  saldo: '85.40',
  monto_proyectado: null,
  vencida: false,
  fecha_emision: null,
  fecha_vencimiento: '2026-10-25',
  fecha_estimada: null,
  fecha_corte: null,
  pago_minimo: null,
  pago_total: null,
  numero_recibo: null,
  recibo_enlace: null,
  cuota_numero: null,
  cuotas_total: null,
  en_proceso: null,
  orden_urgente: null,
  creado_en: '2026-10-01T10:00:00-05:00',
  comprobantes: [],
  historial_montos: [],
  linea_tiempo: [],
  acciones: ['iniciar_pago', 'comentar'],
} as DetalleDeuda

const montados: VueWrapper[] = []
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  useSesionStore().usuario = { id: 'u1', rol: 'asistente', nombre: 'Ana' }
  simulada.obtenerDeuda.mockResolvedValue(detalle)
  simulada.listarComentarios.mockResolvedValue([])
})
afterEach(() => montados.splice(0).forEach((w) => w.unmount()))

async function montar() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/asistente/deudas/:id', component: DeudaDetallePage }],
  })
  await router.push('/asistente/deudas/d1')
  const vista = mount(defineComponent({ setup: () => () => h(RouterView) }), {
    global: { plugins: [router, [PrimeVue, configuracionUi], ToastService] },
  })
  montados.push(vista)
  await flushPromises()
  return vista
}

describe('pantalla del detalle de deuda', () => {
  it('carga la deuda, inicia el pago y comenta', async () => {
    simulada.iniciarPago.mockResolvedValue({ resultado: 'iniciado', repetido: false })
    simulada.comentarDeuda.mockResolvedValue({
      id: 'k1',
      texto: 'Voy al agente',
      autor: 'Ana',
      rol: 'asistente',
      propio: true,
      creado_en: '2026-10-20T10:00:00-05:00',
    })
    const vista = await montar()

    expect(simulada.obtenerDeuda).toHaveBeenCalledWith('d1', expect.any(AbortSignal))
    await vista.get('.acciones button').trigger('click')
    await flushPromises()
    expect(simulada.iniciarPago).toHaveBeenCalledWith('d1')
    expect(simulada.obtenerDeuda).toHaveBeenCalledTimes(2)

    await vista.get('textarea').setValue('Voy al agente')
    await vista.get('form.escribir').trigger('submit')
    await flushPromises()
    expect(simulada.comentarDeuda).toHaveBeenCalledWith('d1', 'Voy al agente')
    expect(vista.text()).toContain('Voy al agente')
  })

  it('una deuda ajena o inexistente se muestra como no encontrada', async () => {
    simulada.obtenerDeuda.mockRejectedValue({ status: 404, code: 'NO_ENCONTRADO', detail: '' })

    const vista = await montar()

    expect(vista.text()).toContain('Esta deuda no existe o ya no tienes acceso')
  })
})
