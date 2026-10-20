import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import { configuracionUi } from '@/config/ui'
import ServiciosSuperficie from '@/components/servicios/ServiciosSuperficie.vue'
import FormularioServicio from '@/components/servicios/FormularioServicio.vue'
import DialogoBajaServicio from '@/components/servicios/DialogoBajaServicio.vue'
import {
  OTRA_EMPRESA,
  aDatos,
  esquemaServicio,
  lugarEn,
  valoresDe,
  type DatosServicio,
  type Empresa,
  type ServicioDetalle,
} from '@/components/servicios/modelo'

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
}
const hidrandina: Empresa = {
  id: 'e1',
  nombre: 'Hidrandina',
  tipo_servicio: 'luz',
  patron_codigo: '\\d{8}',
}
const movistar: Empresa = {
  id: 'e2',
  nombre: 'Movistar',
  tipo_servicio: 'telecomunicaciones',
  patron_codigo: null,
}
const servicio = (campos: Partial<ServicioDetalle> = {}): ServicioDetalle => ({
  id: 's1',
  categoria: luz,
  empresa_id: 'e1',
  empresa: 'Hidrandina',
  empresa_manual: false,
  codigo_suministro: '12345678',
  titular: 'Carlos Mendoza',
  alias: 'Luz oficina',
  lugar_pago: 'agente_bcp',
  notas: null,
  estado: 'activo',
  deudas_pendientes: 0,
  ...campos,
})
const valido = {
  categoria_id: 'c1',
  empresa: 'e1',
  empresa_nombre: '',
  codigo_suministro: '12345678',
  titular: '',
  alias: '',
  lugar_pago: 'agente_bcp',
  notas: '',
}

const montados: VueWrapper[] = []
const global = {
  plugins: [
    [PrimeVue, configuracionUi] as [typeof PrimeVue, typeof configuracionUi],
    ToastService,
    ConfirmationService,
  ],
}
beforeEach(() => vi.useRealTimers())
afterEach(() => {
  montados.splice(0).forEach((w) => w.unmount())
  document.body.innerHTML = ''
})
function montar<T extends VueWrapper>(w: T) {
  montados.push(w)
  return w
}
const montarLista = (props: Record<string, unknown>) =>
  montar(mount(ServiciosSuperficie, { attachTo: document.body, props, global }))
const montarFormulario = (props: InstanceType<typeof FormularioServicio>['$props']) =>
  montar(mount(FormularioServicio, { attachTo: document.body, props, global }))
const montarBaja = (props: InstanceType<typeof DialogoBajaServicio>['$props']) =>
  montar(mount(DialogoBajaServicio, { attachTo: document.body, props, global }))
const dialogo = () => document.querySelector<HTMLElement>('.p-dialog')!
function escribir(selector: string, valor: string) {
  const campo = document.querySelector<HTMLInputElement | HTMLSelectElement>(selector)!
  campo.value = valor
  campo.dispatchEvent(new Event(campo instanceof HTMLSelectElement ? 'change' : 'input'))
}

describe('reglas del formulario de servicios', () => {
  const esquema = esquemaServicio([hidrandina, movistar])

  it('valida el código con el formato de la empresa cuando lo tiene (CA02)', () => {
    expect(esquema.safeParse(valido).success).toBe(true)
    expect(esquema.safeParse({ ...valido, codigo_suministro: '1234 5678' }).success).toBe(true)
    const corto = esquema.safeParse({ ...valido, codigo_suministro: '1234' })
    expect(corto.error?.issues[0]?.message).toContain('formato de Hidrandina')
    expect(esquema.safeParse({ ...valido, empresa: 'e2', codigo_suministro: 'MV-1' }).success).toBe(
      true,
    )
    expect(esquema.safeParse({ ...valido, codigo_suministro: '  ' }).success).toBe(false)
  })

  it('«Otra empresa» exige su nombre (CA01)', () => {
    const sinNombre = esquema.safeParse({ ...valido, empresa: OTRA_EMPRESA })
    expect(sinNombre.error?.issues[0]?.path).toEqual(['empresa_nombre'])
    expect(
      esquema.safeParse({ ...valido, empresa: OTRA_EMPRESA, empresa_nombre: 'Electro Oriente' })
        .success,
    ).toBe(true)
    expect(esquema.safeParse({ ...valido, lugar_pago: '' }).success).toBe(false)
  })

  it('traduce entre valores del formulario y datos de la API', () => {
    expect(
      aDatos({ ...valido, alias: ' Luz oficina ', empresa: OTRA_EMPRESA, empresa_nombre: 'X' }),
    ).toEqual({
      categoria_id: 'c1',
      empresa_id: null,
      empresa_nombre: 'X',
      codigo_suministro: '12345678',
      titular: null,
      alias: 'Luz oficina',
      lugar_pago: 'agente_bcp',
      notas: null,
    })
    expect(
      valoresDe(servicio({ empresa_id: null, empresa: 'Electro', empresa_manual: true })),
    ).toMatchObject({ empresa: OTRA_EMPRESA, empresa_nombre: 'Electro' })
    expect(valoresDe(null).empresa).toBe('')
    expect(lugarEn('banca_movil')).toBe('banca móvil o Yape')
    expect(lugarEn(null)).toBeNull()
  })
})

describe('lista de servicios', () => {
  it('muestra cada servicio con su código y lugar de pago, y acciones según el rol (CA08)', () => {
    const w = montarLista({
      servicios: [servicio(), servicio({ id: 's2', alias: null, estado: 'baja' })],
      total: 2,
      categorias: [luz],
      estado: 'todos',
    })
    const [activo, baja] = w.findAll('.servicio')
    expect(activo!.text()).toContain('Luz oficina')
    expect(activo!.get('.codigo').text()).toBe('12345678')
    expect(activo!.text()).toContain('Se paga en un agente BCP')
    expect(baja!.text()).toContain('Hidrandina De baja')
    expect(w.find('button[aria-label^="Dar de baja"]').exists()).toBe(false)
    expect(baja!.find('button[aria-label^="Editar"]').exists()).toBe(false)
  })

  it('el gerente da de baja y reactiva', async () => {
    const w = montarLista({
      servicios: [servicio(), servicio({ id: 's2', estado: 'baja' })],
      total: 2,
      puedeDarDeBaja: true,
      estado: 'todos',
    })
    await w.get('button[aria-label="Dar de baja Luz oficina"]').trigger('click')
    await w.get('button[aria-label="Reactivar Luz oficina"]').trigger('click')
    await w.get('button[aria-label="Editar Luz oficina"]').trigger('click')
    expect(w.emitted('baja')).toEqual([['s1']])
    expect(w.emitted('reactivar')).toEqual([['s2']])
    expect(w.emitted('editar')).toEqual([['s1']])
  })

  it('busca al dejar de escribir y filtra por categoría y estado (CA10)', async () => {
    vi.useFakeTimers()
    const w = montarLista({ servicios: [servicio()], total: 1, categorias: [luz] })

    await w.get('input[type="search"]').setValue('hidr')
    await w.get('input[type="search"]').setValue('hidra ')
    expect(w.emitted('buscar')).toBeUndefined()
    vi.advanceTimersByTime(300)
    expect(w.emitted('buscar')).toEqual([['hidra']])

    await w.findAll('.chip')[1]!.trigger('click')
    await w.findAll('.estados button')[1]!.trigger('click')
    expect(w.emitted('filtrarCategoria')).toEqual([['c1']])
    expect(w.emitted('filtrarEstado')).toEqual([['baja']])
  })

  it('distingue la lista vacía de la búsqueda sin resultados, y tiene carga, error y más', async () => {
    const w = montarLista({})
    expect(w.text()).toContain('Todavía no registras servicios')
    await w.get('.vacio button').trigger('click')
    expect(w.emitted('crear')).toHaveLength(1)

    await w.setProps({ busqueda: 'nada' })
    expect(w.text()).toContain('Ningún servicio coincide')
    await w.setProps({ estadoPantalla: 'cargando' })
    expect(w.find('[aria-busy="true"]').exists()).toBe(true)
    await w.setProps({ estadoPantalla: 'error' })
    await w.get('[role="alert"] button').trigger('click')
    expect(w.emitted('reintentar')).toHaveLength(1)

    await w.setProps({ estadoPantalla: 'lista', servicios: [servicio()], total: 5, hayMas: true })
    expect(w.get('.mas').text()).toContain('Ves 1 de 5')
    await w.get('.mas button').trigger('click')
    expect(w.emitted('mas')).toHaveLength(1)
  })
})

describe('formulario de servicio', () => {
  it('registra un servicio con empresa manual (CA01 a CA06)', async () => {
    const guardar = vi.fn<(d: DatosServicio) => Promise<unknown>>().mockResolvedValue(undefined)
    montarFormulario({ empresas: [hidrandina, movistar], categorias: [luz], guardar })
    await flushPromises()

    escribir('select[name="empresa"]', OTRA_EMPRESA)
    await flushPromises()
    escribir('[name="empresa_nombre"]', 'Electro Oriente')
    escribir('[name="codigo_suministro"]', 'AG-2231')
    escribir('[name="alias"]', 'Luz casa')
    escribir('select[name="categoria_id"]', 'c1')
    document.querySelector<HTMLInputElement>('.lugares input[value="ventanilla_empresa"]')!.click()
    escribir('textarea[name="notas"]', 'Pedir boleta.')
    await flushPromises()
    dialogo().querySelector('form')!.dispatchEvent(new Event('submit'))

    await vi.waitFor(() =>
      expect(guardar).toHaveBeenCalledWith({
        categoria_id: 'c1',
        empresa_id: null,
        empresa_nombre: 'Electro Oriente',
        codigo_suministro: 'AG-2231',
        titular: null,
        alias: 'Luz casa',
        lugar_pago: 'ventanilla_empresa',
        notas: 'Pedir boleta.',
      }),
    )
  })

  it('advierte las deudas pendientes solo si cambia el código (CA07)', async () => {
    montarFormulario({
      servicio: servicio({ deudas_pendientes: 2 }),
      empresas: [hidrandina],
      categorias: [luz],
      guardar: vi.fn<(d: DatosServicio) => Promise<unknown>>(),
    })
    await flushPromises()
    expect(dialogo().textContent).not.toContain('deudas pendientes')

    escribir('[name="codigo_suministro"]', '87654321')
    await flushPromises()

    expect(dialogo().querySelector('.aviso')!.textContent).toContain(
      'Tiene 2 deudas pendientes con el código 12345678',
    )
  })

  it('un código duplicado de la API se marca en su campo (CA03)', async () => {
    const guardar = vi.fn<(d: DatosServicio) => Promise<unknown>>().mockRejectedValue({
      status: 409,
      code: 'DUPLICADO',
      detail: 'Ya registraste este servicio.',
      field: 'codigo_suministro',
    })
    montarFormulario({
      servicio: servicio(),
      empresas: [hidrandina],
      categorias: [luz],
      guardar,
    })
    await flushPromises()
    escribir('[name="titular"]', 'Otra persona')
    await flushPromises()
    dialogo().querySelector('form')!.dispatchEvent(new Event('submit'))

    await vi.waitFor(() => expect(dialogo().textContent).toContain('Ya registraste este servicio.'))
  })
})

describe('baja de un servicio', () => {
  it('explica qué pasa y confirma (CA08)', async () => {
    const confirmar = vi.fn<() => Promise<unknown>>().mockResolvedValue(undefined)
    montarBaja({ servicio: servicio({ deudas_pendientes: 3 }), confirmar })
    await flushPromises()

    expect(dialogo().textContent).toContain('Las 3 deudas pendientes se conservan')
    ;[...dialogo().querySelectorAll('button')]
      .find((b) => b.textContent?.includes('Dar de baja'))!
      .click()
    await flushPromises()
    expect(confirmar).toHaveBeenCalled()
  })

  it('muestra el error si falla', async () => {
    const confirmar = vi.fn<() => Promise<unknown>>().mockRejectedValue({ detail: '' })
    montarBaja({ servicio: servicio(), confirmar })
    await flushPromises()

    ;[...dialogo().querySelectorAll('button')]
      .find((b) => b.textContent?.includes('Dar de baja'))!
      .click()
    await flushPromises()
    expect(dialogo().querySelector('[role="alert"]')!.textContent).toContain(
      'No pudimos darlo de baja',
    )
  })
})
