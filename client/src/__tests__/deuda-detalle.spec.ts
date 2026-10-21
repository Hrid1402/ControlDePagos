import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import { configuracionUi } from '@/config/ui'
import DeudaDetalleSuperficie from '@/components/deudas/DeudaDetalleSuperficie.vue'
import { textoEvento, type DetalleDeuda } from '@/components/deudas/detalle'

const detalle = (cambios: Partial<DetalleDeuda> = {}): DetalleDeuda => ({
  id: 'd1',
  servicio: {
    id: 's1',
    empresa: 'Hidrandina',
    alias: 'Luz de la casa',
    codigo_suministro: '12345678',
    titular: null,
    lugar_pago: 'agente_bcp',
    notas: null,
  },
  categoria: {
    id: 'c1',
    nombre: 'Luz',
    color: '#F59E0B',
    icono: 'pi-bolt',
    tipo: 'servicio_variable',
  },
  periodo: '2026-10',
  estado: 'pagada_parcial',
  origen: 'manual',
  moneda: 'PEN',
  monto: '100.00',
  pagado: '40.00',
  saldo: '60.00',
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
      id: 'c1',
      estado: 'rechazado',
      motivo_codigo: 'ilegible',
      observacion: 'Toma otra foto.',
      monto: null,
      monto_aplicado: '60.00',
      moneda: 'PEN',
      subido_por: 'Ana',
      creado_en: '2026-10-20T10:00:00-05:00',
      reemplaza_a_id: null,
    },
  ],
  historial_montos: [],
  linea_tiempo: [
    { tipo: 'comprobante_rechazado', fecha: '2026-10-20T10:01:00-05:00', actor: null, detalle: {} },
  ],
  acciones: ['iniciar_pago', 'comentar'],
  ...cambios,
})
const montar = (d: DetalleDeuda) =>
  mount(DeudaDetalleSuperficie, {
    props: { detalle: d, hoy: '2026-10-20' },
    global: { plugins: [[PrimeVue, configuracionUi]] },
  })

describe('detalle de deuda (H17)', () => {
  it('muestra saldo, comprobantes con su motivo y solo las acciones recibidas', async () => {
    const vista = montar(detalle())

    expect(vista.text()).toMatch(/Saldo por pagar\s*S\/\s60\.00/)
    expect(vista.text()).toContain('Toma otra foto.')
    expect(vista.text()).toContain('El comprobante se rechazó')
    expect(vista.text()).not.toContain('Adjuntar comprobante')
    await vista.get('.acciones button').trigger('click')
    expect(vista.emitted('accion')).toEqual([['iniciar_pago']])
  })

  it('una deuda anulada no tiene acciones ni deja comentar', () => {
    const vista = montar(detalle({ estado: 'anulada', acciones: [] }))

    expect(vista.text()).toContain('Esta deuda está anulada')
    expect(vista.find('.acciones').exists()).toBe(false)
    expect(vista.find('textarea').exists()).toBe(false)
  })

  it('envía comentarios de hasta 500 caracteres', async () => {
    const vista = montar(detalle())
    await vista.get('textarea').setValue('  Pagué en el agente  ')
    await vista.get('form.escribir').trigger('submit')
    expect(vista.emitted('comentar')).toEqual([['Pagué en el agente']])

    await vista.get('textarea').setValue('x'.repeat(501))
    expect(vista.text()).toContain('Sobran 1 caracteres')
  })

  it('nombra cada evento de la línea de tiempo', () => {
    expect(textoEvento({ tipo: 'pago_iniciado', fecha: '', actor: null, detalle: {} })).toBe(
      'Empezó a pagarla',
    )
    expect(textoEvento({ tipo: 'evento_nuevo', fecha: '', actor: null, detalle: {} })).toBe(
      'Evento nuevo',
    )
  })
})
