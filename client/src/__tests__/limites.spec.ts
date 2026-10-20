import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import { configuracionUi } from '@/config/ui'
import LimitesSuperficie from '@/components/limites/LimitesSuperficie.vue'
import SolicitudesSuperficie from '@/components/limites/SolicitudesSuperficie.vue'
import {
  esquemaLimites,
  fechaCorta,
  monto,
  venceHoy,
  type Solicitud,
} from '@/components/limites/modelo'

const hoy = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Lima' })
const solicitud = (campos: Partial<Solicitud> = {}): Solicitud => ({
  id: 's1',
  servicio: 'Luz del departamento',
  asistente: 'Rosa Melgar',
  monto: '480.00',
  moneda: 'PEN',
  estado: 'pendiente',
  fecha_vencimiento: '2026-11-20',
  creado_en: '2026-10-18T09:00:00-05:00',
  motivo: null,
  resuelta_por: null,
  resuelta_en: null,
  ...campos,
})

// El Textarea de PrimeVue con auto-resize observa su tamaño; jsdom no trae ResizeObserver.
vi.stubGlobal(
  'ResizeObserver',
  class {
    observe() {}
    disconnect() {}
  },
)
const montados: VueWrapper[] = []
afterEach(() => {
  montados.splice(0).forEach((w) => w.unmount())
  document.body.innerHTML = ''
})
const global = {
  plugins: [
    [PrimeVue, configuracionUi] as [typeof PrimeVue, typeof configuracionUi],
    ToastService,
    ConfirmationService,
  ],
}
function montarLimites(props: Record<string, unknown> = {}) {
  const guardar = vi.fn<(valores: Record<string, unknown>) => Promise<unknown>>()
  guardar.mockResolvedValue(undefined)
  const vista = mount(LimitesSuperficie, {
    attachTo: document.body,
    props: { guardar, ...props },
    global,
  })
  montados.push(vista)
  return { vista, guardar }
}
function montarSolicitudes(props: Record<string, unknown> = {}) {
  const vista = mount(SolicitudesSuperficie, { attachTo: document.body, props, global })
  montados.push(vista)
  return vista
}

describe('reglas del formulario de límites', () => {
  it('acepta soles con hasta dos decimales y vacío como sin límite (CA02, CA03)', () => {
    expect(esquemaLimites.safeParse({ por_pago: '150.5', mensual: '' }).success).toBe(true)
    expect(esquemaLimites.safeParse({ por_pago: '', mensual: '' }).success).toBe(true)
    expect(esquemaLimites.safeParse({ por_pago: '10.123', mensual: '' }).success).toBe(false)
    expect(esquemaLimites.safeParse({ por_pago: '0', mensual: '' }).success).toBe(false)
    expect(esquemaLimites.safeParse({ por_pago: '-5', mensual: '' }).success).toBe(false)
  })

  it('no deja un límite por pago mayor que el mensual', () => {
    const r = esquemaLimites.safeParse({ por_pago: '900', mensual: '500' })
    expect(r.success).toBe(false)
    expect(r.error?.issues[0]?.path).toEqual(['por_pago'])
  })

  it('formatea montos y fechas de Lima', () => {
    expect(monto('1500')).toContain('1,500.00')
    expect(monto(20, 'USD')).toContain('20.00')
    expect(fechaCorta('2026-10-25')).toBe('25 de octubre')
    expect(venceHoy(hoy)).toBe(true)
    expect(venceHoy('2000-01-01')).toBe(false)
  })
})

describe('superficie de límites', () => {
  it('muestra el consumo validado y en proceso frente al límite mensual (CA04)', () => {
    const { vista } = montarLimites({
      limites: { por_pago: '300', mensual: '1000' },
      consumo: { validado: '400', reservado: '100' },
    })
    const barra = vista.get('[role="meter"]')
    expect(barra.attributes('aria-valuenow')).toBe('500')
    expect(barra.attributes('aria-valuemax')).toBe('1000')
    expect(vista.get('.tramo.validado').attributes('style')).toContain('width: 40%')
    expect(vista.get('.tramo.reservado').attributes('style')).toContain('width: 10%')
    expect(vista.get('.desglose').text()).toContain('Disponible')
    expect(vista.get<HTMLInputElement>('[name="mensual"]').element.value).toBe('1000')
  })

  it('avisa cuando el consumo pasa el límite mensual', () => {
    const { vista } = montarLimites({
      limites: { por_pago: null, mensual: '200' },
      consumo: { validado: '250', reservado: '0' },
    })
    expect(vista.get('.barra').classes()).toContain('excedida')
    expect(vista.get('.desglose').text()).toContain('Sobre el límite')
  })

  it('sin límite mensual no dibuja la barra y deja los campos vacíos (CA03)', () => {
    const { vista } = montarLimites()
    expect(vista.find('[role="meter"]').exists()).toBe(false)
    expect(vista.text()).toContain('sin límite mensual')
    expect(vista.get<HTMLInputElement>('[name="por_pago"]').element.value).toBe('')
  })

  it('guarda los límites escritos', async () => {
    const { vista, guardar } = montarLimites()
    await vista.get('[name="por_pago"]').setValue('250.50')
    await vista.get('[name="mensual"]').setValue('2000')
    await vista.get('form').trigger('submit')
    await vi.waitFor(() => expect(guardar).toHaveBeenCalled())
    expect(guardar.mock.calls[0]?.[0]).toMatchObject({ por_pago: '250.50', mensual: '2000' })
  })

  it('no guarda si el límite por pago supera al mensual', async () => {
    const { vista, guardar } = montarLimites()
    await vista.get('[name="por_pago"]').setValue('900')
    await vista.get('[name="mensual"]').setValue('500')
    await vista.get('form').trigger('submit')
    await vi.waitFor(() => expect(vista.text()).toContain('no puede ser mayor que el mensual'))
    expect(guardar).not.toHaveBeenCalled()
  })

  it('muestra carga y error con reintento', async () => {
    const { vista } = montarLimites({ estadoPantalla: 'cargando' })
    expect(vista.find('[aria-busy="true"]').exists()).toBe(true)
    await vista.setProps({ estadoPantalla: 'error' })
    await vista.get('[role="alert"] button').trigger('click')
    expect(vista.emitted('reintentar')).toHaveLength(1)
  })
})

describe('solicitudes de aprobación', () => {
  it('filtra por estado y cuenta las pendientes', async () => {
    const vista = montarSolicitudes({
      solicitudes: [solicitud(), solicitud({ id: 's2', estado: 'aprobada' })],
      pendientes: 1,
    })
    expect(vista.findAll('.solicitud')).toHaveLength(1)
    expect(vista.get('button[aria-pressed="true"]').text()).toContain('1')
    await vista.findAll('.filtros button')[1]!.trigger('click')
    expect(vista.emitted('filtrar')?.[0]).toEqual(['aprobada'])
  })

  it('marca las que vencen hoy y las de dólares (CA09)', () => {
    const vista = montarSolicitudes({
      solicitudes: [solicitud({ fecha_vencimiento: hoy, moneda: 'USD', monto: '35' })],
    })
    expect(vista.get('.solicitud').classes()).toContain('urgente')
    expect(vista.text()).toContain('Vence hoy')
    expect(vista.text()).toContain('En dólares, siempre requiere tu aprobación')
  })

  it('aprueba con un clic', async () => {
    const vista = montarSolicitudes({ solicitudes: [solicitud()] })
    await vista.get('button[aria-label^="Aprobar"]').trigger('click')
    expect(vista.emitted('aprobar')?.[0]).toEqual(['s1'])
  })

  it('rechaza con motivo opcional y permite cancelar (CA08)', async () => {
    const vista = montarSolicitudes({ solicitudes: [solicitud()] })
    await vista.get('button[aria-label^="Rechazar"]').trigger('click')
    await nextTick()
    expect(document.activeElement?.id).toBe('motivo-s1')
    await vista.get('.rechazo button[type="button"]').trigger('click')
    expect(vista.find('.rechazo').exists()).toBe(false)

    await vista.get('button[aria-label^="Rechazar"]').trigger('click')
    await vista.get('#motivo-s1').setValue('  Ya lo pagué yo  ')
    await vista.get('.rechazo').trigger('submit')
    expect(vista.emitted('rechazar')?.[0]).toEqual(['s1', 'Ya lo pagué yo'])

    await vista.get('button[aria-label^="Rechazar"]').trigger('click')
    await vista.get('.rechazo').trigger('submit')
    await flushPromises()
    expect(vista.emitted('rechazar')?.[1]).toEqual(['s1', null])
  })

  it('muestra quién resolvió y el motivo del rechazo', () => {
    const resueltas = [
      solicitud({
        estado: 'aprobada',
        resuelta_por: 'Carlos',
        resuelta_en: '2026-10-19T10:00:00-05:00',
      }),
      solicitud({
        id: 's2',
        estado: 'rechazada',
        motivo: 'Monto alto',
        resuelta_en: '2026-10-19T10:00:00-05:00',
      }),
    ]
    const aprobadas = montarSolicitudes({ solicitudes: resueltas, filtro: 'aprobada' })
    expect(aprobadas.text()).toContain('Aprobada por Carlos')
    expect(aprobadas.text()).toContain('Solo autoriza este monto')
    const rechazadas = montarSolicitudes({ solicitudes: resueltas, filtro: 'rechazada' })
    expect(rechazadas.text()).toContain('Motivo: Monto alto')
    expect(rechazadas.find('.acciones').exists()).toBe(false)
  })

  it('tiene vacíos, carga y error', async () => {
    const vista = montarSolicitudes({ filtro: 'rechazada' })
    expect(vista.text()).toContain('Todavía no rechazaste solicitudes.')
    await vista.setProps({ estadoPantalla: 'cargando' })
    expect(vista.find('[aria-busy="true"]').exists()).toBe(true)
    await vista.setProps({ estadoPantalla: 'error' })
    await vista.get('[role="alert"] button').trigger('click')
    expect(vista.emitted('reintentar')).toHaveLength(1)
  })
})
