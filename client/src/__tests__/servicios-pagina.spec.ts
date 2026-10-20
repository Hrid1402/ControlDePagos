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
import ServiciosPage from '@/pages/ServiciosPage.vue'
import * as api from '@/api/servicios'
import * as apiCategorias from '@/api/categorias'
import { useSesionStore } from '@/stores/sesion'
import type { Categoria } from '@/components/categorias/modelo'
import type { ServicioDetalle } from '@/components/servicios/modelo'

vi.mock('@/api/servicios', () => ({
  TAMANO_PAGINA: 30,
  listarServicios: vi.fn<typeof api.listarServicios>(),
  obtenerServicio: vi.fn<typeof api.obtenerServicio>(),
  listarEmpresas: vi.fn<typeof api.listarEmpresas>(),
  crearServicio: vi.fn<typeof api.crearServicio>(),
  editarServicio: vi.fn<typeof api.editarServicio>(),
  darDeBajaServicio: vi.fn<typeof api.darDeBajaServicio>(),
  reactivarServicio: vi.fn<typeof api.reactivarServicio>(),
}))
vi.mock('@/api/categorias', () => ({ listarCategorias: vi.fn() }))
const simulada = vi.mocked(api)
const categoriasSimuladas = vi.mocked(apiCategorias)

vi.stubGlobal(
  'ResizeObserver',
  class {
    observe() {}
    disconnect() {}
  },
)

const luz = {
  id: 'c1',
  nombre: 'Luz',
  tipo: 'servicio_variable',
  color: '#F59E0B',
  icono: 'pi-bolt',
} as Categoria
const servicio = (campos: Partial<ServicioDetalle> = {}): ServicioDetalle => ({
  id: 's1',
  categoria: luz,
  empresa_id: 'e1',
  empresa: 'Enel',
  empresa_manual: false,
  codigo_suministro: '12345678',
  titular: null,
  alias: 'Luz oficina',
  lugar_pago: 'agente_bcp',
  notas: null,
  estado: 'activo',
  deudas_pendientes: 0,
  ...campos,
})

const montados: VueWrapper[] = []
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  useSesionStore().usuario = { id: 'u1', rol: 'gerente', nombre: 'Carlos' }
  simulada.listarServicios.mockResolvedValue({ items: [servicio()], total: 1, page: 1 })
  simulada.listarEmpresas.mockResolvedValue([
    { id: 'e1', nombre: 'Enel', tipo_servicio: 'luz', patron_codigo: null },
  ])
  categoriasSimuladas.listarCategorias.mockResolvedValue([luz])
})
afterEach(() => {
  montados.splice(0).forEach((w) => w.unmount())
  document.body.innerHTML = ''
})

async function montar(ruta = '/gerente/servicios') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/gerente/servicios', component: ServiciosPage }],
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
const dialogo = () => document.querySelector<HTMLElement>('.p-dialog')
const toast = () => document.querySelector('.p-toast')?.textContent ?? ''
function escribir(selector: string, valor: string) {
  const campo = document.querySelector<HTMLInputElement | HTMLSelectElement>(selector)!
  campo.value = valor
  campo.dispatchEvent(new Event(campo instanceof HTMLSelectElement ? 'change' : 'input'))
}

describe('pantalla de servicios', () => {
  it('lista con los filtros de la URL y categorías para filtrar (CA10)', async () => {
    const { wrapper } = await montar('/gerente/servicios?q=luz&categoria=c1&estado=todos')

    expect(simulada.listarServicios).toHaveBeenCalledWith(
      { q: 'luz', categoria_id: 'c1', estado: 'todos' },
      1,
      expect.any(AbortSignal),
    )
    expect(wrapper.get('.servicio').text()).toContain('Luz oficina')
    expect(wrapper.get('.chip[aria-pressed="true"]').text()).toBe('Luz')
  })

  it('buscar y filtrar actualizan la URL sin perder los demás filtros', async () => {
    vi.useFakeTimers()
    const { wrapper, router } = await montar('/gerente/servicios?categoria=c1')

    await wrapper.get('input[type="search"]').setValue('enel')
    vi.advanceTimersByTime(300)
    vi.useRealTimers()
    await wrapper.findAll('.estados button')[1]!.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ categoria: 'c1', q: 'enel', estado: 'baja' })
    expect(simulada.listarServicios).toHaveBeenLastCalledWith(
      { q: 'enel', categoria_id: 'c1', estado: 'baja' },
      1,
      expect.any(AbortSignal),
    )
  })

  it('muestra el error y reintenta', async () => {
    simulada.listarServicios.mockRejectedValueOnce(new Error('red'))
    const { wrapper } = await montar()

    await wrapper.get('[role="alert"] button').trigger('click')
    await flushPromises()

    expect(wrapper.get('.servicio').text()).toContain('Luz oficina')
  })

  it('carga la página siguiente sin repetir servicios', async () => {
    simulada.listarServicios
      .mockResolvedValueOnce({ items: [servicio()], total: 2, page: 1 })
      .mockResolvedValueOnce({
        items: [servicio(), servicio({ id: 's2', alias: 'Agua casa' })],
        total: 2,
        page: 2,
      })
    const { wrapper } = await montar()

    await wrapper.get('.mas button').trigger('click')
    await flushPromises()

    expect(simulada.listarServicios).toHaveBeenLastCalledWith(
      { q: '', categoria_id: '', estado: 'activo' },
      2,
    )
    expect(wrapper.findAll('.servicio')).toHaveLength(2)
  })

  it('registra un servicio y recarga la lista (CA01 a CA06)', async () => {
    simulada.crearServicio.mockResolvedValue(servicio({ id: 's2' }))
    const { wrapper } = await montar()

    await wrapper.get('.encabezado button').trigger('click')
    await flushPromises()
    escribir('select[name="empresa"]', 'e1')
    escribir('[name="codigo_suministro"]', '87654321')
    escribir('select[name="categoria_id"]', 'c1')
    document.querySelector<HTMLInputElement>('.lugares input[value="agente_kasnet"]')!.click()
    await flushPromises()
    dialogo()!.querySelector('form')!.dispatchEvent(new Event('submit'))
    await flushPromises()

    expect(simulada.crearServicio).toHaveBeenCalledWith(
      expect.objectContaining({
        empresa_id: 'e1',
        codigo_suministro: '87654321',
        lugar_pago: 'agente_kasnet',
      }),
    )
    expect(simulada.listarServicios).toHaveBeenCalledTimes(2)
    expect(dialogo()).toBeNull()
  })

  it('edita con el detalle al día y advierte las deudas del código anterior (CA07)', async () => {
    simulada.obtenerServicio.mockResolvedValue(servicio({ deudas_pendientes: 2 }))
    simulada.editarServicio.mockResolvedValue({
      ...servicio({ codigo_suministro: '99999999' }),
      advertencias: { codigo_cambiado: true, deudas_pendientes: 2 },
    })
    const { wrapper } = await montar()

    await wrapper.get('button[aria-label="Editar Luz oficina"]').trigger('click')
    await flushPromises()
    expect(simulada.obtenerServicio).toHaveBeenCalledWith('s1')
    escribir('[name="codigo_suministro"]', '99999999')
    await flushPromises()
    expect(dialogo()!.querySelector('.aviso')!.textContent).toContain('2 deudas pendientes')
    dialogo()!.querySelector('form')!.dispatchEvent(new Event('submit'))
    await flushPromises()

    expect(simulada.editarServicio).toHaveBeenCalledWith(
      's1',
      expect.objectContaining({ codigo_suministro: '99999999' }),
    )
    expect(toast()).toContain('2 deudas pendientes registradas con el código anterior')
  })

  it('el gerente da de baja con confirmación y reactiva (CA08)', async () => {
    simulada.obtenerServicio.mockResolvedValue(servicio({ deudas_pendientes: 1 }))
    simulada.darDeBajaServicio.mockResolvedValue(servicio({ estado: 'baja' }))
    const { wrapper } = await montar()

    await wrapper.get('button[aria-label="Dar de baja Luz oficina"]').trigger('click')
    await flushPromises()
    ;[...dialogo()!.querySelectorAll('button')]
      .find((b) => b.textContent?.includes('Dar de baja'))!
      .click()
    await flushPromises()
    expect(simulada.darDeBajaServicio).toHaveBeenCalledWith('s1')
    expect(toast()).toContain('ya no genera deudas nuevas')

    simulada.listarServicios.mockResolvedValue({
      items: [servicio({ estado: 'baja' })],
      total: 1,
      page: 1,
    })
    simulada.reactivarServicio.mockResolvedValue(servicio())
    await wrapper.findAll('.estados button')[1]!.trigger('click')
    await flushPromises()
    await wrapper.get('button[aria-label="Reactivar Luz oficina"]').trigger('click')
    await flushPromises()
    expect(simulada.reactivarServicio).toHaveBeenCalledWith('s1')
    expect(toast()).toContain('volvió a tu lista de activos')
  })

  it('la asistente registra y edita, pero no da de baja (CA09)', async () => {
    useSesionStore().usuario = { id: 'u2', rol: 'asistente', nombre: 'Rosa' }
    const { wrapper } = await montar()

    expect(wrapper.find('button[aria-label="Editar Luz oficina"]').exists()).toBe(true)
    expect(wrapper.find('button[aria-label^="Dar de baja"]').exists()).toBe(false)
  })

  it('si el servicio ya no existe al abrirlo, avisa y recarga', async () => {
    simulada.obtenerServicio.mockRejectedValue({ status: 404, detail: 'No se encontró.' })
    const { wrapper } = await montar()

    await wrapper.get('button[aria-label="Editar Luz oficina"]').trigger('click')
    await flushPromises()

    expect(toast()).toContain('No se encontró.')
    expect(dialogo()).toBeNull()
    expect(simulada.listarServicios).toHaveBeenCalledTimes(2)
  })
})
