import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import Toast from 'primevue/toast'
import { configuracionUi } from '@/config/ui'
import CategoriasPage from '@/pages/CategoriasPage.vue'
import * as api from '@/api/categorias'
import { useSesionStore } from '@/stores/sesion'
import {
  destinosPara,
  esquemaCategoria,
  tintaSobre,
  type Categoria,
} from '@/components/categorias/modelo'

vi.mock('@/api/categorias', () => ({
  listarCategorias: vi.fn<typeof api.listarCategorias>(),
  crearCategoria: vi.fn<typeof api.crearCategoria>(),
  editarCategoria: vi.fn<typeof api.editarCategoria>(),
  eliminarCategoria: vi.fn<typeof api.eliminarCategoria>(),
}))
const simulada = vi.mocked(api)

const categoria = (campos: Partial<Categoria> = {}): Categoria => ({
  id: 'c1',
  nombre: 'Luz',
  color: '#F59E0B',
  icono: 'pi-bolt',
  tipo: 'servicio_variable',
  precargada: true,
  cantidad_servicios: 3,
  cantidad_deudas: 3,
  ...campos,
})
const luz = categoria()
const colegio = categoria({
  id: 'c2',
  nombre: 'Colegio',
  color: '#2563EB',
  icono: 'pi-graduation-cap',
  tipo: 'monto_fijo',
  precargada: false,
  cantidad_servicios: 0,
  cantidad_deudas: 0,
})
const gimnasio = categoria({
  id: 'c3',
  nombre: 'Gimnasio',
  tipo: 'monto_fijo',
  precargada: false,
  cantidad_servicios: 2,
  cantidad_deudas: 1,
})
const club = categoria({
  id: 'c4',
  nombre: 'Club',
  tipo: 'monto_fijo',
  precargada: false,
  cantidad_servicios: 0,
  cantidad_deudas: 0,
})

const montados: VueWrapper[] = []
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  simulada.listarCategorias.mockResolvedValue([luz, colegio, gimnasio])
})
afterEach(() => {
  montados.splice(0).forEach((w) => w.unmount())
  document.body.innerHTML = ''
})

async function montar(rol: 'gerente' | 'asistente' = 'gerente') {
  useSesionStore().usuario = { id: 'u1', rol, nombre: 'Carlos' }
  const wrapper = mount(
    defineComponent({ setup: () => () => h('div', [h(CategoriasPage), h(Toast)]) }),
    {
      attachTo: document.body,
      global: { plugins: [[PrimeVue, configuracionUi], ToastService, ConfirmationService] },
    },
  )
  montados.push(wrapper)
  await flushPromises()
  return wrapper
}
const dialogo = () => document.querySelector<HTMLElement>('.p-dialog')
const boton = (texto: string, raiz: ParentNode | null = document) =>
  [...(raiz?.querySelectorAll('button') ?? [])].find((b) => b.textContent?.includes(texto)) as
    HTMLButtonElement | undefined
function escribir(selector: string, valor: string) {
  const campo = document.querySelector<HTMLInputElement | HTMLSelectElement>(selector)!
  campo.value = valor
  campo.dispatchEvent(new Event(campo instanceof HTMLSelectElement ? 'change' : 'input'))
}

describe('reglas de la pantalla', () => {
  it('elige una tinta legible sobre cada color', () => {
    expect(tintaSobre('#F59E0B')).toBe('#192c29')
    expect(tintaSobre('#075A50')).toBe('#ffffff')
  })

  it('con deudas solo ofrece destinos del mismo tipo (CA03)', () => {
    expect(destinosPara(gimnasio, [luz, colegio, gimnasio, club]).map((c) => c.id)).toEqual([
      'c2',
      'c4',
    ])
    expect(destinosPara(colegio, [luz, colegio, gimnasio]).map((c) => c.id)).toEqual(['c1', 'c3'])
  })

  it('valida nombre, tipo, color e ícono (CA02)', () => {
    const valido = { nombre: ' Colegio ', tipo: 'monto_fijo', color: '#2563EB', icono: 'pi-tag' }
    expect(esquemaCategoria.safeParse(valido).success).toBe(true)
    expect(esquemaCategoria.safeParse({ ...valido, nombre: '  ' }).success).toBe(false)
    expect(esquemaCategoria.safeParse({ ...valido, nombre: 'x'.repeat(41) }).success).toBe(false)
    expect(esquemaCategoria.safeParse({ ...valido, tipo: '' }).success).toBe(false)
  })
})

describe('pantalla de categorías', () => {
  it('separa precargadas y propias con sus servicios y deudas (CA01 y CA06)', async () => {
    const wrapper = await montar()

    const [precargadas, propias] = wrapper.findAll('.grupo')
    expect(precargadas!.text()).toContain('Luz')
    expect(propias!.findAll('.ficha')).toHaveLength(2)
    const fichaLuz = precargadas!.get('.ficha')
    expect(fichaLuz.get('.cifras').text()).toBe('Servicios3Deudas3')
    expect(fichaLuz.find('button[aria-label="Eliminar Luz"]').exists()).toBe(false)
    expect(propias!.find('button[aria-label="Eliminar Colegio"]').exists()).toBe(true)
  })

  it('sin categorías propias invita a crear una', async () => {
    simulada.listarCategorias.mockResolvedValue([luz])
    const wrapper = await montar()
    expect(wrapper.text()).toContain('Todavía no creaste categorías propias')
  })

  it('la asistente crea pero no edita ni elimina (CA04)', async () => {
    const wrapper = await montar('asistente')
    expect(wrapper.find('.acciones').exists()).toBe(false)
    expect(boton('Nueva categoría')).toBeDefined()
  })

  it('si la carga falla permite reintentar', async () => {
    simulada.listarCategorias.mockRejectedValueOnce({ status: 500 })
    const wrapper = await montar()
    await wrapper.get('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.ficha')).toHaveLength(3)
  })

  it('crea una categoría con tipo, color e ícono (CA02 y CA03)', async () => {
    simulada.crearCategoria.mockResolvedValue(colegio)
    await montar()

    boton('Nueva categoría')!.click()
    await flushPromises()
    escribir('[name="nombre"]', 'Colegio')
    document.querySelector<HTMLInputElement>('.tipos input[value="monto_fijo"]')!.click()
    document.querySelector<HTMLInputElement>('.muestras input[value="#2563EB"]')!.click()
    document.querySelector<HTMLInputElement>('.muestras input[value="pi-graduation-cap"]')!.click()
    await flushPromises()
    expect(dialogo()!.textContent).toContain('Así se verá: Colegio, monto fijo.')
    dialogo()!.querySelector('form')!.dispatchEvent(new Event('submit'))

    await vi.waitFor(() =>
      expect(simulada.crearCategoria).toHaveBeenCalledWith({
        nombre: 'Colegio',
        tipo: 'monto_fijo',
        color: '#2563EB',
        icono: 'pi-graduation-cap',
      }),
    )
    await vi.waitFor(() => expect(dialogo()).toBeNull())
    expect(simulada.listarCategorias).toHaveBeenCalledTimes(2)
  })

  it('un nombre repetido se marca en su campo', async () => {
    simulada.crearCategoria.mockRejectedValue({
      status: 409,
      code: 'CATEGORIA_DUPLICADA',
      detail: "Ya existe una categoría con el nombre 'luz'.",
      field: 'nombre',
    })
    await montar()

    boton('Nueva categoría')!.click()
    await flushPromises()
    escribir('[name="nombre"]', 'luz')
    document.querySelector<HTMLInputElement>('.tipos input[value="servicio_variable"]')!.click()
    await flushPromises()
    dialogo()!.querySelector('form')!.dispatchEvent(new Event('submit'))

    await vi.waitFor(() => expect(dialogo()!.textContent).toContain('Ya existe una categoría'))
  })

  it('al editar una con deudas el tipo queda fijo y lo explica (CA03)', async () => {
    simulada.editarCategoria.mockResolvedValue({ ...luz, nombre: 'Electricidad' })
    const wrapper = await montar()

    await wrapper.get('button[aria-label="Editar Luz"]').trigger('click')
    await flushPromises()
    expect(document.querySelector<HTMLFieldSetElement>('fieldset.tipos')!.disabled).toBe(true)
    expect(dialogo()!.textContent).toContain('ya tiene deudas registradas')
    escribir('[name="nombre"]', 'Electricidad')
    await flushPromises()
    dialogo()!.querySelector('form')!.dispatchEvent(new Event('submit'))

    await vi.waitFor(() =>
      expect(simulada.editarCategoria).toHaveBeenCalledWith(
        'c1',
        expect.objectContaining({ nombre: 'Electricidad', tipo: 'servicio_variable' }),
      ),
    )
  })

  it('elimina una sin servicios con confirmación', async () => {
    simulada.eliminarCategoria.mockResolvedValue(0)
    const wrapper = await montar()

    await wrapper.get('button[aria-label="Eliminar Colegio"]').trigger('click')
    await flushPromises()
    expect(dialogo()!.textContent).toContain('No tiene servicios')
    boton('Eliminar', dialogo())!.click()
    await flushPromises()

    expect(simulada.eliminarCategoria).toHaveBeenCalledWith('c2', undefined)
    expect(document.body.textContent).toContain('Colegio se eliminó.')
  })

  it('con servicios pide a dónde moverlos y solo ofrece el mismo tipo si hay deudas (CA05)', async () => {
    simulada.listarCategorias.mockResolvedValue([luz, colegio, gimnasio])
    simulada.eliminarCategoria.mockResolvedValue(2)
    const wrapper = await montar()

    await wrapper.get('button[aria-label="Eliminar Gimnasio"]').trigger('click')
    await flushPromises()
    const opciones = [...dialogo()!.querySelectorAll('option')].map((o) => o.textContent)
    expect(opciones).toEqual(['Elige una categoría', 'Colegio'])
    expect(boton('Mover y eliminar', dialogo())!.disabled).toBe(true)

    escribir('.p-dialog select', 'c2')
    await flushPromises()
    boton('Mover y eliminar', dialogo())!.click()
    await flushPromises()

    expect(simulada.eliminarCategoria).toHaveBeenCalledWith('c3', 'c2')
    expect(document.body.textContent).toContain('2 servicios pasaron a otra categoría')
  })

  it('sin destino compatible explica que hay que crear uno', async () => {
    simulada.listarCategorias.mockResolvedValue([luz, { ...gimnasio, tipo: 'prestamo' }])
    const wrapper = await montar()

    await wrapper.get('button[aria-label="Eliminar Gimnasio"]').trigger('click')
    await flushPromises()

    expect(dialogo()!.textContent).toContain('Crea una primero')
    expect(boton('Mover y eliminar', dialogo())!.disabled).toBe(true)
  })

  it('muestra el conflicto que devuelve la API', async () => {
    simulada.eliminarCategoria.mockRejectedValue({
      status: 409,
      code: 'TIPO_INCOMPATIBLE',
      detail: 'Sus servicios tienen deudas o recurrencias.',
      field: 'mover_a',
    })
    const wrapper = await montar()

    await wrapper.get('button[aria-label="Eliminar Colegio"]').trigger('click')
    await flushPromises()
    boton('Eliminar', dialogo())!.click()
    await flushPromises()

    expect(dialogo()!.querySelector('[role="alert"]')!.textContent).toContain(
      'tienen deudas o recurrencias',
    )
  })
})
