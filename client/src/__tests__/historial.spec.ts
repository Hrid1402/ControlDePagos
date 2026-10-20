import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import PrimeVue from 'primevue/config'
import { configuracionUi } from '@/config/ui'
import HistorialPage from '@/pages/HistorialPage.vue'
import * as api from '@/api/historial'
import * as apiAsistentes from '@/api/asistentes'
import { useSesionStore } from '@/stores/sesion'
import {
  accionDe,
  datosDe,
  dispositivo,
  fraseDe,
  tituloDia,
  type RegistroHistorial,
} from '@/components/historial/modelo'

vi.mock('@/api/historial', () => ({
  TAMANO_PAGINA: 2,
  listarHistorial: vi.fn<typeof api.listarHistorial>(),
  exportarHistorial: vi.fn<typeof api.exportarHistorial>(),
}))
vi.mock('@/api/asistentes', () => ({
  listarAsistentes: vi.fn<typeof apiAsistentes.listarAsistentes>(),
}))
const simulada = vi.mocked(api)
const asistentes = vi.mocked(apiAsistentes)

const GERENTE = 'g1'
const ROSA = 'a1'
const registro = (campos: Partial<RegistroHistorial> = {}): RegistroHistorial => ({
  id: 'r1',
  usuario_id: ROSA,
  usuario_nombre: 'Rosa Melgar',
  accion: 'pago_iniciado',
  entidad: 'deuda',
  entidad_id: 'd1',
  detalle: { saldo: '85.40', estado_anterior: 'pendiente' },
  dispositivo: 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/141.0 Mobile Safari',
  ip: '190.12.3.4',
  creado_en: '2026-10-20T15:30:00-05:00',
  ...campos,
})
const pagina = (items: RegistroHistorial[], total = items.length, page = 1) => ({
  items,
  total,
  page,
})

const montados: VueWrapper[] = []
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-10-20T18:00:00-05:00') })
  asistentes.listarAsistentes.mockResolvedValue([
    {
      id: ROSA,
      nombres: 'Rosa',
      apellidos: 'Melgar',
      username: 'rmelgar',
      estado: 'activa',
      ultimo_ingreso: null,
      creado_en: '2026-10-01T10:00:00-05:00',
    },
  ])
})
afterEach(() => {
  vi.useRealTimers()
  montados.splice(0).forEach((w) => w.unmount())
  document.body.innerHTML = ''
})

async function montar(ruta = '/gerente/historial') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/gerente/historial', component: HistorialPage }],
  })
  await router.push(ruta)
  await router.isReady()
  useSesionStore().usuario = { id: GERENTE, rol: 'gerente', nombre: 'Carlos Mendoza' }
  const wrapper = mount(HistorialPage, {
    attachTo: document.body,
    global: { plugins: [router, [PrimeVue, configuracionUi]] },
  })
  montados.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}
const ultimosFiltros = () => simulada.listarHistorial.mock.lastCall?.[0]

describe('lectura de los registros', () => {
  it('traduce acciones y nombra la cuenta afectada', () => {
    const activacion = registro({
      usuario_id: GERENTE,
      usuario_nombre: 'Carlos Mendoza',
      accion: 'cuenta_activada',
      entidad: 'usuario',
      entidad_id: ROSA,
      detalle: {},
    })
    expect(fraseDe(activacion, { [ROSA]: 'Rosa Melgar' })).toBe('activó la cuenta de Rosa Melgar')
    // Una cuenta eliminada ya no está en la lista: se usa el nombre que guardó el registro.
    const baja = { ...activacion, accion: 'cuenta_eliminada', detalle: { nombre: 'Ana Ruiz' } }
    expect(fraseDe(baja, {})).toBe('eliminó la cuenta de Ana Ruiz')
    expect(fraseDe({ ...activacion, entidad_id: 'otra' }, {})).toBe(
      'activó una cuenta de asistente',
    )
    const propia = registro({
      accion: 'contrasena_restablecida',
      entidad: 'usuario',
      entidad_id: ROSA,
    })
    expect(fraseDe(propia, {})).toBe('restableció su contraseña')
    expect(accionDe('accion_futura').frase).toBe('accion futura')
  })

  it('muestra el detalle sin identificadores internos', () => {
    expect(
      datosDe({
        solicitud_id: 'x',
        iniciado_por: 'y',
        monto: { anterior: '100.00', nuevo: '120.50' },
        vencida: false,
        motivo: null,
        estado_nuevo: 'en_proceso',
        cuenta: '01a15b02-b917-7b9a-9ef2-beeb656c06c8',
      }),
    ).toEqual([
      { campo: 'Monto', valor: 'de 100.00 a 120.50' },
      { campo: 'Ya vencida', valor: 'No' },
      { campo: 'Estado nuevo', valor: 'en proceso' },
    ])
  })

  it('resume el dispositivo y nombra los días', () => {
    expect(dispositivo(registro().dispositivo)).toBe('Chrome en Android')
    expect(dispositivo('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Version/17.0 Safari/604.1')).toBe(
      'Safari en iPhone o iPad',
    )
    expect(dispositivo('pruebas')).toBe('pruebas')
    expect(dispositivo(null)).toBeNull()
    expect(tituloDia('2026-10-20')).toBe('Hoy')
    expect(tituloDia('2026-10-19')).toBe('Ayer')
    expect(tituloDia('2026-10-14')).toBe('Miércoles, 14 de octubre')
    expect(tituloDia('2025-12-31')).toContain('2025')
  })
})

describe('pantalla de historial', () => {
  it('agrupa por día, marca lo propio y despliega el detalle (CA01)', async () => {
    simulada.listarHistorial.mockResolvedValue(
      pagina([
        registro(),
        registro({
          id: 'r2',
          usuario_id: GERENTE,
          usuario_nombre: 'Carlos Mendoza',
          accion: 'login_fallido',
          detalle: {},
          creado_en: '2026-10-19T09:05:00-05:00',
        }),
      ]),
    )
    const { wrapper } = await montar()

    expect(wrapper.findAll('.dia h2').map((h) => h.text())).toEqual(['Hoy', 'Ayer'])
    const [pago, fallido] = wrapper.findAll('.registro')
    expect(pago!.text()).toContain('Rosa Melgar inició un pago')
    expect(pago!.text()).toContain('15:30')
    expect(pago!.text()).toContain('Chrome en Android')
    expect(fallido!.classes()).toContain('alerta')
    expect(fallido!.get('.monograma').text()).toBe('Tú')
    expect(wrapper.get('.conteo').text()).toBe('2 registros')

    const alternar = pago!.get('button.alternar')
    await alternar.trigger('click')
    expect(alternar.attributes('aria-expanded')).toBe('true')
    expect(pago!.get('.detalle').text()).toContain('Saldo')
    expect(pago!.get('.detalle').text()).toContain('190.12.3.4')
  })

  it('lee los filtros de la URL y los guarda al cambiarlos (CA03)', async () => {
    simulada.listarHistorial.mockResolvedValue(pagina([registro()]))
    const { wrapper, router } = await montar('/gerente/historial?accion=pago_iniciado')

    expect(ultimosFiltros()).toEqual({
      usuario: '',
      accion: 'pago_iniciado',
      desde: '',
      hasta: '',
    })
    expect(wrapper.get<HTMLSelectElement>('#historial-accion').element.value).toBe('pago_iniciado')
    expect(wrapper.get('#historial-usuario').text()).toContain('Tú (Carlos Mendoza)')
    expect(wrapper.get('#historial-usuario').text()).toContain('Rosa Melgar')

    await wrapper.get('#historial-usuario').setValue(ROSA)
    await wrapper.get('#historial-desde').setValue('2026-10-01')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({
      accion: 'pago_iniciado',
      usuario: ROSA,
      desde: '2026-10-01',
    })
    expect(ultimosFiltros()).toEqual({
      usuario: ROSA,
      accion: 'pago_iniciado',
      desde: '2026-10-01',
      hasta: '',
    })
    expect(wrapper.get('.conteo').text()).toContain('con estos filtros')

    await wrapper.get('button.quitar').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({})
  })

  it('no consulta con un rango de fechas al revés', async () => {
    simulada.listarHistorial.mockResolvedValue(pagina([]))
    const { wrapper } = await montar('/gerente/historial?desde=2026-10-20&hasta=2026-10-01')

    expect(simulada.listarHistorial).not.toHaveBeenCalled()
    expect(wrapper.get('#historial-error-fechas').text()).toContain('posterior a la inicial')
    expect(wrapper.get('#historial-hasta').attributes('aria-invalid')).toBe('true')
  })

  it('distingue el historial vacío del filtro sin resultados', async () => {
    simulada.listarHistorial.mockResolvedValue(pagina([]))
    const { wrapper } = await montar()
    expect(wrapper.text()).toContain('Todavía no hay acciones registradas')
    expect(wrapper.get('.encabezado button').attributes('disabled')).toBeDefined()

    const filtrada = await montar('/gerente/historial?accion=login_fallido')
    expect(filtrada.wrapper.text()).toContain('Ningún registro coincide con estos filtros')
  })

  it('si la carga falla permite reintentar sin perder los filtros', async () => {
    simulada.listarHistorial.mockRejectedValueOnce({ status: 500 })
    simulada.listarHistorial.mockResolvedValueOnce(pagina([registro()]))
    const { wrapper } = await montar('/gerente/historial?accion=pago_iniciado')

    expect(wrapper.get('[role="alert"]').text()).toContain('No pudimos cargar el historial')
    await wrapper.get('.fallo button').trigger('click')
    await flushPromises()

    expect(ultimosFiltros()?.accion).toBe('pago_iniciado')
    expect(wrapper.findAll('.registro')).toHaveLength(1)
  })

  it('muestra más registros sin repetir los que ya están', async () => {
    simulada.listarHistorial
      .mockResolvedValueOnce(pagina([registro({ id: 'r1' }), registro({ id: 'r2' })], 3))
      .mockResolvedValueOnce(pagina([registro({ id: 'r2' }), registro({ id: 'r3' })], 3, 2))
    const { wrapper } = await montar()

    expect(wrapper.get('.mas').text()).toContain('Ves 2 de 3')
    await wrapper.get('.mas button').trigger('click')
    await flushPromises()

    expect(simulada.listarHistorial.mock.lastCall?.[1]).toBe(2)
    expect(wrapper.findAll('.registro')).toHaveLength(3)
    expect(wrapper.find('.mas').exists()).toBe(false)
  })

  it('exporta a Excel con los mismos filtros (CA05)', async () => {
    simulada.listarHistorial.mockResolvedValue(pagina([registro()]))
    simulada.exportarHistorial.mockResolvedValue(new Blob(['x']))
    URL.createObjectURL = vi.fn<typeof URL.createObjectURL>(() => 'blob:historial')
    URL.revokeObjectURL = vi.fn<typeof URL.revokeObjectURL>()
    const clic = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const { wrapper } = await montar('/gerente/historial?usuario=a1')

    await wrapper.get('.encabezado button').trigger('click')
    await flushPromises()

    expect(simulada.exportarHistorial).toHaveBeenCalledWith({
      usuario: ROSA,
      accion: '',
      desde: '',
      hasta: '',
    })
    expect(clic).toHaveBeenCalled()
    clic.mockRestore()
  })

  it('avisa si la exportación falla', async () => {
    simulada.listarHistorial.mockResolvedValue(pagina([registro()]))
    simulada.exportarHistorial.mockRejectedValue({ detail: '' })
    const { wrapper } = await montar()

    await wrapper.get('.encabezado button').trigger('click')
    await flushPromises()

    expect(wrapper.get('.aviso-error').text()).toBe('No pudimos exportar el historial.')
  })
})
