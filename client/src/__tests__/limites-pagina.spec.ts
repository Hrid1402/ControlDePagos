import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import Toast from 'primevue/toast'
import { configuracionUi } from '@/config/ui'
import LimitesPage from '@/pages/LimitesPage.vue'
import * as api from '@/api/limites'
import type { Solicitud } from '@/components/limites/modelo'

vi.mock('@/api/limites', () => ({
  TAMANO_SOLICITUDES: 50,
  obtenerLimites: vi.fn<typeof api.obtenerLimites>(),
  definirLimites: vi.fn<typeof api.definirLimites>(),
  listarSolicitudes: vi.fn<typeof api.listarSolicitudes>(),
  aprobarSolicitud: vi.fn<typeof api.aprobarSolicitud>(),
  rechazarSolicitud: vi.fn<typeof api.rechazarSolicitud>(),
}))
const simulada = vi.mocked(api)

// El Textarea de PrimeVue con auto-resize observa su tamaño; jsdom no trae ResizeObserver.
vi.stubGlobal(
  'ResizeObserver',
  class {
    observe() {}
    disconnect() {}
  },
)

const solicitud = (campos: Partial<Solicitud> = {}): Solicitud => ({
  id: 's1',
  servicio: 'Luz del departamento',
  asistente: 'Rosa Melgar',
  monto: '480.00',
  moneda: 'PEN',
  estado: 'pendiente',
  fecha_vencimiento: '2026-11-20',
  creado_en: '2026-10-20T09:00:00-05:00',
  motivo: null,
  resuelta_por: null,
  resuelta_en: null,
  ...campos,
})
const limites = (campos: Partial<api.LimitesConsumo> = {}): api.LimitesConsumo => ({
  por_pago: '300.00',
  mensual: '1500.00',
  mes: '2026-10',
  consumo: { validado: '400.00', reservado: '100.00' },
  ...campos,
})

const montados: VueWrapper[] = []
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  simulada.obtenerLimites.mockResolvedValue(limites())
  simulada.listarSolicitudes.mockImplementation(async (estado) =>
    estado === 'pendiente'
      ? { items: [solicitud(), solicitud({ id: 's2', servicio: 'Agua' })], total: 2 }
      : { items: [solicitud({ id: 's9', estado })], total: 1 },
  )
})
afterEach(() => {
  montados.splice(0).forEach((w) => w.unmount())
  document.body.innerHTML = ''
})

async function montar(ruta = '/gerente/limites') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/gerente/limites', component: LimitesPage }],
  })
  await router.push(ruta)
  await router.isReady()
  const wrapper = mount(
    defineComponent({ setup: () => () => h('div', [h(RouterView), h(Toast)]) }),
    {
      attachTo: document.body,
      global: {
        plugins: [router, [PrimeVue, configuracionUi], ToastService, ConfirmationService],
      },
    },
  )
  montados.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}
const toast = () => document.querySelector('.p-toast')?.textContent ?? ''

describe('pantalla de límites y aprobaciones', () => {
  it('muestra los límites, el consumo y las solicitudes pendientes (CA04 y CA10)', async () => {
    const { wrapper } = await montar()

    expect(wrapper.get('[role="meter"]').attributes('aria-valuenow')).toBe('500')
    expect(wrapper.get<HTMLInputElement>('[name="por_pago"]').element.value).toBe('300.00')
    expect(wrapper.findAll('.solicitud')).toHaveLength(2)
    expect(wrapper.get('.filtros button[aria-pressed="true"]').text()).toContain('2')
  })

  it('el filtro va a la URL y el contador de pendientes se conserva', async () => {
    const { wrapper, router } = await montar()

    await wrapper.findAll('.filtros button')[1]!.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ ver: 'aprobada' })
    expect(simulada.listarSolicitudes).toHaveBeenCalledWith('aprobada')
    expect(wrapper.findAll('.solicitud')).toHaveLength(1)
    expect(wrapper.get('.contador').text()).toBe('2')
  })

  it('un filtro desconocido en la URL muestra las pendientes', async () => {
    const { wrapper } = await montar('/gerente/limites?ver=otra')
    expect(wrapper.get('.filtros button[aria-pressed="true"]').text()).toContain('Pendientes')
  })

  it('aprobar avisa, recarga y no deja responder dos veces a la vez (CA07)', async () => {
    let terminar: (s: Solicitud) => void = () => {}
    simulada.aprobarSolicitud.mockReturnValue(new Promise((r) => (terminar = r)))
    const { wrapper } = await montar()
    const llamadasAntes = simulada.listarSolicitudes.mock.calls.length

    await wrapper.get('button[aria-label^="Aprobar"]').trigger('click')
    await wrapper.findAll('button[aria-label^="Aprobar"]')[1]!.trigger('click')
    terminar(solicitud({ estado: 'aprobada' }))
    await flushPromises()

    expect(simulada.aprobarSolicitud).toHaveBeenCalledTimes(1)
    expect(simulada.aprobarSolicitud).toHaveBeenCalledWith('s1')
    expect(toast()).toContain('Rosa Melgar ya puede pagar')
    expect(simulada.listarSolicitudes.mock.calls.length).toBeGreaterThan(llamadasAntes)
  })

  it('si la solicitud ya cambió avisa y recarga (409)', async () => {
    simulada.aprobarSolicitud.mockRejectedValue({
      status: 409,
      code: 'SOLICITUD_YA_RESUELTA',
      detail: 'La solicitud ya ha sido resuelta.',
      field: null,
    })
    const { wrapper } = await montar()

    await wrapper.get('button[aria-label^="Aprobar"]').trigger('click')
    await flushPromises()

    expect(toast()).toContain('La solicitud ya cambió')
    expect(toast()).toContain('ya ha sido resuelta')
  })

  it('rechaza con el motivo escrito (CA08)', async () => {
    simulada.rechazarSolicitud.mockResolvedValue(solicitud({ estado: 'rechazada' }))
    const { wrapper } = await montar()

    await wrapper.get('button[aria-label^="Rechazar"]').trigger('click')
    await wrapper.get('#motivo-s1').setValue('Este mes lo pago yo')
    await wrapper.get('.rechazo').trigger('submit')
    await flushPromises()

    expect(simulada.rechazarSolicitud).toHaveBeenCalledWith('s1', 'Este mes lo pago yo')
    expect(toast()).toContain('Le avisamos a Rosa Melgar')
  })

  it('guarda los límites y actualiza el consumo (CA01 a CA03)', async () => {
    simulada.definirLimites.mockResolvedValue(
      limites({ por_pago: null, mensual: '2000.00', consumo: { validado: '0', reservado: '0' } }),
    )
    const { wrapper } = await montar()

    await wrapper.get('[name="por_pago"]').setValue('')
    await wrapper.get('[name="mensual"]').setValue('2000')
    await wrapper.get('.limites form').trigger('submit')
    await flushPromises()

    expect(simulada.definirLimites).toHaveBeenCalledWith(
      expect.objectContaining({ por_pago: '', mensual: '2000' }),
    )
    await vi.waitFor(() =>
      expect(wrapper.get('[role="meter"]').attributes('aria-valuemax')).toBe('2000'),
    )
  })

  it('un error de la API se muestra en su campo', async () => {
    simulada.definirLimites.mockRejectedValue({
      status: 400,
      code: 'LIMITE_INVALIDO',
      detail: 'El límite por pago no puede ser mayor que el mensual.',
      field: 'por_pago',
    })
    const { wrapper } = await montar()

    await wrapper.get('[name="por_pago"]').setValue('900')
    await wrapper.get('.limites form').trigger('submit')
    await flushPromises()

    await vi.waitFor(() => expect(wrapper.text()).toContain('no puede ser mayor que el mensual'))
  })

  it('si fallan las cargas permite reintentar cada parte', async () => {
    simulada.obtenerLimites.mockRejectedValueOnce({ status: 500 })
    simulada.listarSolicitudes.mockRejectedValueOnce({ status: 500 })
    const { wrapper } = await montar()

    const fallos = wrapper.findAll('[role="alert"]')
    expect(fallos).toHaveLength(2)
    await fallos[0]!.get('button').trigger('click')
    await fallos[1]!.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.find('[role="meter"]').exists()).toBe(true)
    expect(wrapper.findAll('.solicitud')).toHaveLength(2)
  })

  it('muestra más solicitudes sin repetirlas', async () => {
    simulada.listarSolicitudes.mockImplementation(async (_estado, pagina = 1) =>
      pagina === 1
        ? { items: [solicitud(), solicitud({ id: 's2' })], total: 3 }
        : { items: [solicitud({ id: 's2' }), solicitud({ id: 's3' })], total: 3 },
    )
    const { wrapper } = await montar()

    await wrapper.get('.mas button').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.solicitud')).toHaveLength(3)
    expect(wrapper.find('.mas').exists()).toBe(false)
  })

  it('al volver a la pestaña lee de nuevo solicitudes y consumo', async () => {
    await montar()
    const antes = simulada.obtenerLimites.mock.calls.length

    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()

    expect(simulada.obtenerLimites.mock.calls.length).toBe(antes + 1)
  })
})
