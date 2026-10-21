import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import PrimeVue from 'primevue/config'
import Toast from 'primevue/toast'
import ToastService from 'primevue/toastservice'
import { configuracionUi } from '@/config/ui'
import RutaPage from '@/pages/RutaPage.vue'
import * as rutaApi from '@/api/ruta'
import * as comprobantes from '@/api/comprobantes'
import { useSesionStore } from '@/stores/sesion'
import type { ItemRuta, Ruta } from '@/components/ruta/modelo'

vi.mock('@/api/ruta', () => ({ obtenerRuta: vi.fn(), iniciarRuta: vi.fn(), marcarPagada: vi.fn() }))
vi.mock('@/api/comprobantes', () => ({ subirComprobante: vi.fn() }))
const api = vi.mocked(rutaApi)
const subir = vi.mocked(comprobantes.subirComprobante)

const item = (id: string, cambios: Partial<ItemRuta> = {}): ItemRuta => ({
  id,
  empresa: 'Hidrandina',
  alias: `Deuda ${id}`,
  codigo_suministro: '123',
  categoria: { id: 'c1', nombre: 'Luz', color: '#F59E0B', icono: 'pi-bolt', tipo: 'x' },
  monto: '85.40',
  saldo: '85.40',
  moneda: 'PEN',
  estado: 'pendiente',
  fecha_vencimiento: '2026-10-25',
  en_ruta: false,
  pago_realizado: false,
  pago_realizado_en: null,
  comprobante_estado: null,
  ...cambios,
})
const enRuta = { estado: 'en_proceso', en_ruta: true }
const ruta = (items: ItemRuta[]): Ruta => ({
  grupos: [{ lugar: 'agente_bcp', items, totales: { PEN: '0', USD: '0' } }],
  totales: { PEN: '0', USD: '0' },
})

const montados: VueWrapper[] = []
beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  useSesionStore().usuario = { id: 'u1', rol: 'asistente', nombre: 'Ana' }
  api.obtenerRuta.mockResolvedValue(ruta([item('d1'), item('d2', { saldo: '62.10' })]))
})
afterEach(() => {
  montados.splice(0).forEach((w) => w.unmount())
  document.body.innerHTML = ''
})

async function montar(url = '/asistente/ruta') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/asistente/ruta', name: 'asistente-ruta', component: RutaPage },
      { path: '/asistente', name: 'asistente-inicio', component: { render: () => null } },
      { path: '/asistente/deudas/:id', name: 'asistente-deuda', component: { render: () => null } },
    ],
  })
  await router.push(url)
  const vista = mount(defineComponent({ setup: () => () => h('div', [h(RouterView), h(Toast)]) }), {
    global: { plugins: [router, [PrimeVue, configuracionUi], ToastService] },
    attachTo: document.body,
  })
  montados.push(vista)
  await flushPromises()
  return { vista, router }
}

const boton = (vista: VueWrapper, texto: string) =>
  vista.findAll('button').find((b) => b.text().includes(texto))!

describe('pantalla de la ruta de pagos (H23)', () => {
  it('trae lo elegido en la bandeja, solo si sigue disponible, y limpia la URL (CA02)', async () => {
    api.obtenerRuta.mockResolvedValue(ruta([item('d1'), item('d2', enRuta)]))
    const { vista, router } = await montar('/asistente/ruta?deudas=d1,d2,otra')

    expect(router.currentRoute.value.query).toEqual({})
    expect(vista.text()).toContain('1 deuda · llevar')
    expect(
      vista.get<HTMLInputElement>('input[aria-label="Agregar Deuda d1 a la ruta"]').element.checked,
    ).toBe(true)
  })

  it('inicia lo elegido y explica lo que no se inició', async () => {
    api.iniciarRuta.mockResolvedValue({
      resultados: [
        { deuda_id: 'd1', resultado: 'iniciada', codigo: null, mensaje: null, repetido: false },
        {
          deuda_id: 'd2',
          resultado: 'requiere_aprobacion',
          codigo: null,
          mensaje: null,
          repetido: false,
        },
      ],
      totales: { PEN: '85.40', USD: '0.00' },
    })
    const { vista } = await montar()
    await vista.get('input[aria-label="Elegir todas las deudas de Agente BCP"]').setValue(true)
    expect(vista.text()).toContain('2 deudas · llevar')

    await boton(vista, 'Iniciar ruta').trigger('click')
    await flushPromises()

    expect(api.iniciarRuta).toHaveBeenCalledWith(['d1', 'd2'])
    expect(api.obtenerRuta).toHaveBeenCalledTimes(2)
    expect(vista.text()).toContain('Iniciaste 1 pago')
    expect(vista.text()).toContain('Deuda d2 · necesita la aprobación del gerente')
  })

  it('marca cada pago al avanzar y recuerda los vouchers al terminar (CA03, CA04)', async () => {
    api.obtenerRuta
      .mockResolvedValueOnce(ruta([item('d1', enRuta)]))
      .mockResolvedValue(ruta([item('d1', { ...enRuta, pago_realizado: true })]))
    api.marcarPagada.mockResolvedValue()
    const { vista } = await montar()

    await boton(vista, 'Marcar pagada').trigger('click')
    await flushPromises()

    expect(api.marcarPagada).toHaveBeenCalledWith('d1')
    expect(vista.text()).toContain('Terminaste la ruta')
    expect(vista.text()).toContain('falta 1')
  })

  it('adjunta el voucher y avisa si ya se usó en otra deuda', async () => {
    api.obtenerRuta.mockResolvedValue(ruta([item('d1', { ...enRuta, pago_realizado: true })]))
    subir.mockRejectedValue({
      status: 409,
      code: 'DUPLICADO',
      detail: 'Este comprobante ya fue registrado.',
    })
    const { vista } = await montar()

    await boton(vista, 'Adjuntar comprobante').trigger('click')
    const entrada = vista.get<HTMLInputElement>('input[type=file]')
    const archivo = new File(['x'], 'voucher.png', { type: 'image/png' })
    Object.defineProperty(entrada.element, 'files', { value: [archivo], configurable: true })
    await entrada.trigger('change')
    await flushPromises()

    expect(subir).toHaveBeenCalledWith('d1', archivo)
    expect(document.body.textContent).toContain('Comprobante repetido')
    expect(document.body.textContent).toContain('Este comprobante ya fue registrado.')
  })
})
