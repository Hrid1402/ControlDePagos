import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import PrimeVue from 'primevue/config'
import Toast from 'primevue/toast'
import ToastService from 'primevue/toastservice'
import { configuracionUi } from '@/config/ui'
import BandejaPage from '@/pages/BandejaPage.vue'
import * as bandeja from '@/api/bandeja'
import * as comprobantes from '@/api/comprobantes'
import * as deudas from '@/api/deudas'
import { useSesionStore } from '@/stores/sesion'
import type { ItemBandeja } from '@/components/bandeja/modelo'

vi.mock('@/api/bandeja', () => ({
  obtenerBandejaCompleta: vi.fn(),
  fijarDeuda: vi.fn(),
  recordarManana: vi.fn(),
}))
vi.mock('@/api/categorias', () => ({ listarCategorias: vi.fn().mockResolvedValue([]) }))
vi.mock('@/api/comprobantes', () => ({ subirComprobante: vi.fn() }))
vi.mock('@/api/deudas', () => ({ iniciarPago: vi.fn() }))
const api = vi.mocked(bandeja)
const subir = vi.mocked(comprobantes.subirComprobante)
const iniciar = vi.mocked(deudas.iniciarPago)

const item = (cambios: Partial<ItemBandeja> = {}): ItemBandeja => ({
  id: 'd1',
  empresa: 'Hidrandina',
  alias: 'Luz de la casa',
  codigo_suministro: '123',
  lugar_pago: null,
  categoria: { id: 'c1', nombre: 'Luz', color: '#F59E0B', icono: 'pi-bolt', tipo: 'x' },
  monto: '85.40',
  moneda: 'PEN',
  saldo: '85.40',
  estado: 'pendiente',
  fecha_vencimiento: '2026-10-25',
  dias_restantes: 5,
  nivel: 5,
  etiqueta: 'proxima',
  fijada: false,
  orden_urgente: null,
  en_proceso: null,
  comprobante_estado: null,
  ...cambios,
})
const contadores = { por_pagar: 1, por_validar: 0, rechazadas: 0 }

const montados: VueWrapper[] = []
beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  useSesionStore().usuario = { id: 'u1', rol: 'asistente', nombre: 'Ana Torres' }
  api.obtenerBandejaCompleta.mockResolvedValue({ items: [item()], total: 1, page: 1, contadores })
})
afterEach(() => montados.splice(0).forEach((w) => w.unmount()))

async function montar(ruta = '/asistente') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/asistente', name: 'asistente-inicio', component: BandejaPage },
      { path: '/asistente/deudas/:id', name: 'asistente-deuda', component: { render: () => null } },
      { path: '/asistente/ruta', name: 'asistente-ruta', component: { render: () => null } },
    ],
  })
  await router.push(ruta)
  // Toast montado para leer los avisos: el comprobante repetido se informa así.
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

async function elegirArchivo(vista: VueWrapper) {
  await boton(vista, 'Adjuntar comprobante').trigger('click')
  const entrada = vista.get<HTMLInputElement>('input[type=file]')
  const archivo = new File(['x'], 'pago.pdf', { type: 'application/pdf' })
  Object.defineProperty(entrada.element, 'files', { value: [archivo], configurable: true })
  await entrada.trigger('change')
  await flushPromises()
  return archivo
}

describe('pantalla de la bandeja (H15)', () => {
  it('es el inicio de la asistente y lee la pestaña y la categoría de la URL (CA01, CA03, CA11)', async () => {
    const { vista, router } = await montar('/asistente?pestana=por_validar&categoria=c1')
    expect(api.obtenerBandejaCompleta).toHaveBeenCalledWith(
      { pestana: 'por_validar', categoria: 'c1' },
      expect.any(AbortSignal),
    )
    expect(vista.get('h1').text()).toBe('Hola, Ana')

    await boton(vista, 'Por pagar').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ categoria: 'c1' })
    expect(api.obtenerBandejaCompleta).toHaveBeenLastCalledWith(
      { pestana: 'por_pagar', categoria: 'c1' },
      expect.any(AbortSignal),
    )
  })

  it('muestra «Todo al día» sin pendientes y el error con reintento (CA10)', async () => {
    api.obtenerBandejaCompleta.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      contadores: { por_pagar: 0, por_validar: 0, rechazadas: 0 },
    })
    const { vista } = await montar()
    expect(vista.text()).toContain('Todo al día')

    api.obtenerBandejaCompleta.mockRejectedValueOnce({ status: 500, detail: 'x' })
    await boton(vista, 'Rechazadas').trigger('click')
    await flushPromises()
    expect(vista.text()).toContain('No pudimos cargar la bandeja.')
    await boton(vista, 'Reintentar').trigger('click')
    await flushPromises()
    expect(vista.findAll('article')).toHaveLength(1)
  })

  it('fija y pospone, y vuelve a pedir el orden al backend (CA07, CA08)', async () => {
    api.fijarDeuda.mockResolvedValue({ id: 'd1', fijada: true, oculta_hasta: null })
    api.recordarManana.mockRejectedValue({ status: 409, detail: 'Tiene una orden urgente.' })
    const { vista } = await montar()

    await vista.get('button[aria-label="Fijar Luz de la casa arriba"]').trigger('click')
    await flushPromises()
    expect(api.fijarDeuda).toHaveBeenCalledWith('d1', true)
    expect(api.obtenerBandejaCompleta).toHaveBeenCalledTimes(2)

    await vista.get('button[aria-label="Recordar Luz de la casa mañana"]').trigger('click')
    await flushPromises()
    expect(api.recordarManana).toHaveBeenCalledWith('d1')
    expect(document.body.textContent).toContain('Tiene una orden urgente.')
  })

  it('inicia el pago antes de adjuntar y avisa si el comprobante ya se usó (CA05)', async () => {
    iniciar.mockResolvedValue({ resultado: 'iniciado', repetido: false })
    subir.mockRejectedValue({
      status: 409,
      code: 'DUPLICADO',
      detail: 'Este comprobante ya fue registrado.',
    })
    const { vista } = await montar()
    const archivo = await elegirArchivo(vista)

    expect(iniciar).toHaveBeenCalledWith('d1')
    expect(subir).toHaveBeenCalledWith('d1', archivo)
    expect(document.body.textContent).toContain('Comprobante repetido')
    expect(document.body.textContent).toContain('Este comprobante ya fue registrado.')
  })

  it('no sube el comprobante si el pago necesita aprobación del gerente', async () => {
    iniciar.mockResolvedValue({ resultado: 'requiere_aprobacion', repetido: false })
    const { vista } = await montar()
    await elegirArchivo(vista)

    expect(subir).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('Se pidió aprobación')
  })

  it('con el pago ya iniciado por ella, adjunta directo', async () => {
    api.obtenerBandejaCompleta.mockResolvedValue({
      items: [
        item({
          estado: 'en_proceso',
          en_proceso: { usuario_id: 'u1', rol: 'asistente', nombre: 'Ana', desde: null },
        }),
      ],
      total: 1,
      page: 1,
      contadores,
    })
    subir.mockResolvedValue({
      id: 'p1',
      estado: 'procesando',
      motivo_codigo: null,
      observacion: null,
      archivo_enlace: null,
    })
    const { vista } = await montar()
    await elegirArchivo(vista)

    expect(iniciar).not.toHaveBeenCalled()
    expect(subir).toHaveBeenCalledOnce()
    expect(document.body.textContent).toContain('Comprobante adjuntado')
  })

  it('lleva la selección a la ruta de pagos (CA12)', async () => {
    const { vista, router } = await montar()
    await vista.get('input[aria-label="Agregar Luz de la casa a la ruta de pagos"]').setValue(true)
    expect(vista.text()).toContain('1 deuda')

    await boton(vista, 'Agregar a la ruta').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('asistente-ruta')
    expect(router.currentRoute.value.query).toEqual({ deudas: 'd1' })
  })
})
