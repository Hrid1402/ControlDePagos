import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import { configuracionUi } from '@/config/ui'
import DeudaDetallePage from '@/pages/DeudaDetallePage.vue'
import * as deudas from '@/api/deudas'
import * as comprobantes from '@/api/comprobantes'
import { useSesionStore } from '@/stores/sesion'
import type { DetalleDeuda } from '@/components/deudas/detalle'

// TASK-109 y TASK-110: la asistente sube el voucher y el gerente lo valida o lo rechaza.
vi.mock('@/api/deudas', () => ({ obtenerDeuda: vi.fn(), listarComentarios: vi.fn() }))
vi.mock('@/api/comprobantes', () => ({
  obtenerComprobante: vi.fn(),
  subirComprobante: vi.fn(),
  aprobarComprobante: vi.fn(),
  rechazarComprobante: vi.fn(),
}))
const api = vi.mocked(deudas)
const voucher = vi.mocked(comprobantes)

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
  estado: 'por_validar',
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
  comprobantes: [
    {
      id: 'v1',
      estado: 'por_confirmar',
      motivo_codigo: null,
      observacion: 'El voucher coincide con la deuda. Falta que el gerente lo valide.',
      monto: '85.40',
      monto_aplicado: '85.40',
      moneda: 'PEN',
      subido_por: 'Ana Torres',
      creado_en: '2026-10-20T10:00:00-05:00',
      reemplaza_a_id: null,
    },
  ],
  historial_montos: [],
  linea_tiempo: [],
  acciones: ['comentar'],
} as DetalleDeuda

const montados: VueWrapper[] = []
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  api.obtenerDeuda.mockResolvedValue(detalle)
  api.listarComentarios.mockResolvedValue([])
})
afterEach(() => {
  montados.splice(0).forEach((w) => w.unmount())
  document.body.innerHTML = ''
})

async function montar(rol: 'gerente' | 'asistente') {
  useSesionStore().usuario = { id: 'u1', rol, nombre: 'Carlos' }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: `/${rol}/deudas/:id`, component: DeudaDetallePage }],
  })
  await router.push(`/${rol}/deudas/d1`)
  const vista = mount(defineComponent({ setup: () => () => h(RouterView) }), {
    global: { plugins: [router, [PrimeVue, configuracionUi], ToastService] },
    attachTo: document.body,
  })
  montados.push(vista)
  await flushPromises()
  return vista
}

const boton = (vista: VueWrapper, texto: string) =>
  vista.findAll('button').find((b) => b.text().includes(texto))

describe('validación del voucher por el gerente', () => {
  it('el gerente valida el voucher por confirmar con un clic', async () => {
    voucher.aprobarComprobante.mockResolvedValue({
      id: 'v1',
      estado: 'validado',
      motivo_codigo: null,
      observacion: null,
      archivo_enlace: null,
    })
    const vista = await montar('gerente')
    expect(vista.text()).toContain('Por validar del gerente')

    await boton(vista, 'Validar pago')!.trigger('click')
    await flushPromises()

    expect(voucher.aprobarComprobante).toHaveBeenCalledWith('v1')
    expect(api.obtenerDeuda).toHaveBeenCalledTimes(2)
  })

  it('para rechazarlo pide el motivo, que recibe la asistente', async () => {
    voucher.rechazarComprobante.mockResolvedValue({
      id: 'v1',
      estado: 'rechazado',
      motivo_codigo: null,
      observacion: null,
      archivo_enlace: null,
    })
    const vista = await montar('gerente')

    await boton(vista, 'Rechazar')!.trigger('click')
    await flushPromises()
    const dialogo = document.body.querySelector('[role="dialog"]')!
    const confirmar = [...dialogo.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('Rechazar voucher'),
    )!
    expect(confirmar.disabled).toBe(true)

    const motivo = dialogo.querySelector('textarea')!
    motivo.value = 'El monto no es el del recibo'
    motivo.dispatchEvent(new Event('input'))
    await flushPromises()
    confirmar.click()
    await flushPromises()

    expect(voucher.rechazarComprobante).toHaveBeenCalledWith('v1', 'El monto no es el del recibo')
  })

  it('la asistente ve que espera al gerente, sin botones para decidir', async () => {
    const vista = await montar('asistente')

    expect(vista.text()).toContain('Falta que el gerente lo valide')
    expect(boton(vista, 'Validar pago')).toBeUndefined()
    expect(boton(vista, 'Rechazar')).toBeUndefined()
  })
})
