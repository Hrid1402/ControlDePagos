import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import { configuracionUi } from '@/config/ui'
import FormularioDeuda from '@/components/deudas/FormularioDeuda.vue'
import CronogramaPrestamo from '@/components/deudas/CronogramaPrestamo.vue'
import {
  aDatos,
  cronograma,
  esquemaDeuda,
  estaVencida,
  periodoDe,
  sumarMeses,
  valoresIniciales,
  type DatosDeuda,
} from '@/components/deudas/modelo'
import type { Servicio } from '@/components/servicios/modelo'

const servicio = (id: string, tipo: string): Servicio => ({
  id,
  categoria: { id: `c-${tipo}`, nombre: tipo, tipo, color: '#F59E0B', icono: 'pi-bolt' },
  empresa_id: null,
  empresa: `Empresa ${id}`,
  empresa_manual: true,
  codigo_suministro: '0001',
  titular: null,
  alias: null,
  lugar_pago: null,
  notas: null,
  estado: 'activo',
})
const SERVICIOS = [
  servicio('luz', 'servicio_variable'),
  servicio('internet', 'monto_fijo'),
  servicio('visa', 'tarjeta'),
  servicio('auto', 'prestamo'),
]
const errores = (valores: Record<string, unknown>) =>
  esquemaDeuda(SERVICIOS)
    .safeParse({ ...valoresIniciales(), ...valores })
    .error?.issues.map((i) => `${i.path.join('.')}: ${i.message}`) ?? []

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
const dialogo = () => document.querySelector<HTMLElement>('.p-dialog')!
function escribir(selector: string, valor: string) {
  const campo = document.querySelector<HTMLInputElement | HTMLSelectElement>(selector)!
  campo.value = valor
  campo.dispatchEvent(new Event(campo instanceof HTMLSelectElement ? 'change' : 'input'))
}
async function abrir(props: Partial<InstanceType<typeof FormularioDeuda>['$props']> = {}) {
  const guardar = vi.fn<(d: DatosDeuda) => Promise<unknown>>().mockResolvedValue(undefined)
  const w = mount(FormularioDeuda, {
    attachTo: document.body,
    props: { servicios: SERVICIOS, guardar, hoy: '2026-10-20', ...props },
    global,
  })
  montados.push(w)
  await flushPromises()
  return { w, guardar }
}
async function elegir(id: string) {
  escribir('select[name="servicio_id"]', id)
  await flushPromises()
}
async function enviar() {
  dialogo().querySelector('form')!.dispatchEvent(new Event('submit'))
  await flushPromises()
}

describe('reglas del formulario de deuda', () => {
  it('servicio variable y monto fijo piden monto positivo y vencimiento (CA01)', () => {
    expect(errores({ servicio_id: 'luz' })).toEqual([
      'monto: Escribe el monto.',
      'fecha_vencimiento: Elige la fecha de vencimiento.',
    ])
    expect(
      errores({ servicio_id: 'internet', monto: '0', fecha_vencimiento: '2026-10-25' }),
    ).toEqual(['monto: Escribe un monto mayor que cero, con hasta 2 decimales.'])
    expect(
      errores({ servicio_id: 'luz', monto: '12.345', fecha_vencimiento: '2026-10-25' }),
    ).toHaveLength(1)
    expect(
      errores({ servicio_id: 'luz', monto: '120.5', fecha_vencimiento: '2026-10-25' }),
    ).toEqual([])
    expect(
      errores({
        servicio_id: 'luz',
        monto: '1',
        fecha_vencimiento: '2026-10-05',
        fecha_emision: '2026-10-06',
      }),
    ).toEqual(['fecha_emision: La emisión no puede ser posterior al vencimiento.'])
  })

  it('tarjeta pide corte, pago y total; el mínimo no supera el total (CA06)', () => {
    expect(errores({ servicio_id: 'visa' })).toEqual([
      'fecha_corte: Elige la fecha de corte.',
      'fecha_vencimiento: Elige la fecha de pago.',
      'monto: Escribe el pago total.',
    ])
    const base = { servicio_id: 'visa', fecha_corte: '2026-10-05', monto: '750' }
    expect(errores({ ...base, fecha_vencimiento: '2026-10-01' })).toEqual([
      'fecha_vencimiento: La fecha de pago es posterior al corte.',
    ])
    expect(errores({ ...base, fecha_vencimiento: '2026-10-30', pago_minimo: '900' })).toEqual([
      'pago_minimo: El pago mínimo no puede superar al total.',
    ])
    expect(errores({ ...base, fecha_vencimiento: '2026-10-30', pago_minimo: '75' })).toEqual([])
  })

  it('préstamo pide total, cuotas enteras y primera fecha (CA07)', () => {
    expect(errores({ servicio_id: 'auto', cuotas_total: '2.5' })).toEqual([
      'monto_total: Escribe el total del préstamo.',
      'cuotas_total: Usa un número entero de 1 a 360.',
      'fecha_primera_cuota: Elige la fecha de la primera.',
    ])
    expect(
      errores({
        servicio_id: 'auto',
        monto_total: '1000',
        cuotas_total: '12',
        fecha_primera_cuota: '2026-11-15',
      }),
    ).toEqual([])
  })

  it('el recibo es opcional y solo PDF o imagen de hasta 10 MB (CA08)', () => {
    const base = { servicio_id: 'luz', monto: '10', fecha_vencimiento: '2026-10-25' }
    const archivo = (tipo: string, bytes = 10) => new File(['x'.repeat(bytes)], 'r', { type: tipo })
    expect(errores({ ...base, recibo: archivo('application/pdf') })).toEqual([])
    expect(errores({ ...base, recibo: archivo('image/png') })).toEqual([])
    expect(errores({ ...base, recibo: archivo('text/plain') })).toEqual([
      'recibo: Adjunta un PDF o una imagen JPG o PNG.',
    ])
    const grande = archivo('application/pdf')
    Object.defineProperty(grande, 'size', { value: 11 * 1024 * 1024 })
    expect(errores({ ...base, recibo: grande })).toEqual(['recibo: El archivo pesa más de 10 MB.'])
  })

  it('solo envía lo que pide el tipo', () => {
    const valores = {
      ...valoresIniciales('visa', 'USD'),
      monto: '750',
      pago_minimo: '75',
      fecha_corte: '2026-10-05',
      fecha_vencimiento: '2026-10-30',
      fecha_emision: '2026-10-01',
      monto_total: '999',
      repetir: true,
    }
    expect(aDatos(valores, 'tarjeta')).toMatchObject({
      moneda: 'USD',
      monto: '750',
      pago_minimo: '75',
      fecha_corte: '2026-10-05',
      fecha_emision: null,
      monto_total: null,
      repetir: false,
    })
    expect(aDatos(valores, 'prestamo')).toMatchObject({
      monto: null,
      fecha_vencimiento: null,
      monto_total: '999',
    })
  })

  it('el cronograma cuadra el total y respeta los meses cortos', () => {
    const cuotas = cronograma('1000', '3', '2026-01-31')
    expect(cuotas.map((c) => [c.fecha, c.monto])).toEqual([
      ['2026-01-31', '333.33'],
      ['2026-02-28', '333.33'],
      ['2026-03-31', '333.34'],
    ])
    expect(sumarMeses('2028-01-31', 1)).toBe('2028-02-29')
    expect(sumarMeses('2026-11-15', 2)).toBe('2027-01-15')
    expect(cronograma('', '3', '2026-01-31')).toEqual([])
    expect(cronograma('100', '0', '2026-01-31')).toEqual([])
    expect(periodoDe('2026-10-25')).toBe('2026-10')
    expect(estaVencida('2026-10-19', '2026-10-20')).toBe(true)
    expect(estaVencida('2026-10-20', '2026-10-20')).toBe(false)
  })
})

describe('formulario de deuda', () => {
  it('registra un recibo del mes vencido con aviso y lo deja programado (CA01, CA02, CA05)', async () => {
    const { guardar } = await abrir()
    await elegir('luz')
    expect(dialogo().textContent).toContain('Recibo del mes')

    escribir('[name="monto"]', '182.40')
    escribir('[name="fecha_vencimiento"]', '2026-10-12')
    document.querySelector<HTMLInputElement>('[name="repetir"]')!.click()
    await flushPromises()
    expect(dialogo().querySelector('.aviso')!.textContent).toContain('venció el 12 de octubre')
    expect(dialogo().textContent).toContain('cada día 12 esperando el recibo')
    expect(dialogo().textContent).toContain('se usa octubre de 2026')
    await enviar()

    expect(guardar).toHaveBeenCalledWith(
      expect.objectContaining({
        servicio_id: 'luz',
        tipo: 'servicio_variable',
        monto: '182.40',
        moneda: 'PEN',
        fecha_vencimiento: '2026-10-12',
        periodo: null,
        repetir: true,
      }),
    )
  })

  it('tarjeta sugiere pagar el total y no ofrece repetir (CA06)', async () => {
    await abrir()
    await elegir('visa')

    expect(dialogo().textContent).toContain('Te sugerimos pagar el total')
    expect(dialogo().querySelector('[name="fecha_corte"]')).not.toBeNull()
    expect(dialogo().querySelector('[name="repetir"]')).toBeNull()
  })

  it('préstamo muestra el cronograma y envía sus datos (CA07 y CA09)', async () => {
    const { guardar } = await abrir()
    await elegir('auto')
    escribir('[name="monto_total"]', '1000')
    escribir('[name="cuotas_total"]', '3')
    escribir('[name="fecha_primera_cuota"]', '2026-01-31')
    await flushPromises()

    expect(dialogo().querySelectorAll('.cronograma li')).toHaveLength(3)
    expect(dialogo().querySelector('[name="monto"]')).toBeNull()
    await enviar()
    expect(guardar).toHaveBeenCalledWith(
      expect.objectContaining({
        tipo: 'prestamo',
        monto_total: '1000',
        cuotas_total: 3,
        fecha_primera_cuota: '2026-01-31',
      }),
    )
  })

  it('muestra la deuda que ya existe y deja abrirla (CA03)', async () => {
    const { w } = await abrir({
      servicioInicial: 'luz',
      duplicada: {
        id: 'd9',
        periodo: '2026-10',
        estado: 'pendiente',
        monto: '182.40',
        moneda: 'PEN',
        fecha_vencimiento: '2026-10-12',
      },
    })

    expect(dialogo().querySelector('.duplicada')!.textContent).toContain(
      'Ya registraste la deuda de octubre de 2026',
    )
    ;[...dialogo().querySelectorAll('button')]
      .find((b) => b.textContent?.includes('Ver esa deuda'))!
      .click()
    expect(w.emitted('verDuplicada')).toEqual([['d9']])
  })

  it('sin servicios activos explica qué hacer', async () => {
    await abrir({ servicios: [] })
    expect(dialogo().textContent).toContain('Todavía no tienes servicios activos')
  })
})

describe('cronograma', () => {
  it('resume las cuotas largas y las muestra todas al pedirlo', async () => {
    const w = mount(CronogramaPrestamo, {
      props: { cuotas: cronograma('1200', '24', '2026-01-10'), moneda: 'USD' },
    })
    expect(w.findAll('li:not(.salto)')).toHaveLength(7)
    expect(w.text()).toContain('24 cuotas')
    await w.get('.ver').trigger('click')
    expect(w.findAll('li')).toHaveLength(24)
    w.unmount()
  })
})
