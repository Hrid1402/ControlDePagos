import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import { configuracionUi } from '@/config/ui'
import DeudasSuperficie from '@/components/deudas/DeudasSuperficie.vue'
import { plazo } from '@/components/deudas/estados'
import { FILTROS_INICIALES, parametrosApi, type ItemDeuda } from '@/components/deudas/listado'

const HOY = '2026-10-20'
const deuda = (cambios: Partial<ItemDeuda> = {}): ItemDeuda => ({
  id: 'd1',
  servicio_id: 's1',
  empresa: 'Hidrandina',
  alias: 'Luz de la casa',
  codigo_suministro: '12345678',
  categoria: {
    id: 'c1',
    nombre: 'Luz',
    color: '#F59E0B',
    icono: 'pi-bolt',
    tipo: 'servicio_variable',
  },
  periodo: '2026-10',
  monto: '85.40',
  moneda: 'PEN',
  pagado: '0.00',
  saldo: '85.40',
  monto_proyectado: null,
  fecha_vencimiento: '2026-10-25',
  vencida: false,
  estado: 'pendiente',
  numero_recibo: null,
  ...cambios,
})
const montar = (props: Record<string, unknown>) =>
  mount(DeudasSuperficie, {
    props: { filtros: { ...FILTROS_INICIALES }, hoy: HOY, ...props },
    global: { plugins: [[PrimeVue, configuracionUi]] },
  })

describe('lista de deudas (H36)', () => {
  it('dice el plazo según el vencimiento', () => {
    expect(plazo('2026-10-20', HOY).texto).toBe('Vence hoy')
    expect(plazo('2026-10-18', HOY)).toEqual({ texto: 'Venció hace 2 días', tono: 'peligro' })
    expect(plazo('2026-10-30', HOY).tono).toBe('neutro')
    expect(plazo('2026-10-01', HOY, true).texto).toBe('')
  })

  it('traduce los atajos de estado a la API', () => {
    expect(parametrosApi({ ...FILTROS_INICIALES, vista: 'vencidas', q: 'luz' })).toEqual({
      orden: 'vencimiento',
      page: 1,
      size: 20,
      q: 'luz',
      vencida: 'true',
    })
    expect(parametrosApi({ ...FILTROS_INICIALES, vista: 'en_curso' }).estado).toEqual([
      'en_proceso',
      'por_validar',
    ])
  })

  it('muestra cada deuda con su estado, saldo y monto por confirmar', async () => {
    const vista = montar({
      items: [
        deuda({ monto: '100.00', pagado: '40.00', saldo: '60.00', estado: 'pagada_parcial' }),
        deuda({
          id: 'd2',
          monto: null,
          saldo: null,
          monto_proyectado: '62.10',
          estado: 'esperando_recibo',
        }),
      ],
      total: 2,
    })

    expect(vista.text()).toContain('Pagada en parte')
    expect(vista.text()).toMatch(/Saldo S\/\s60\.00/)
    expect(vista.text()).toContain('Por confirmar')
    await vista.findAll('tbody tr')[1]!.trigger('click')
    expect(vista.emitted('abrir')).toEqual([['d2']])
  })

  it('filtra, pagina y distingue la lista vacía de la que no coincide', async () => {
    const vista = montar({ items: [deuda()], total: 45 })
    await vista.get('button[aria-pressed="false"]').trigger('click')
    expect(vista.emitted('filtrar')![0]).toEqual([{ vista: 'por_pagar', page: 1 }])
    const botones = vista.findAll('.paginacion button')
    await botones[botones.length - 1]!.trigger('click')
    const filtrados = vista.emitted('filtrar')!
    expect(filtrados[filtrados.length - 1]).toEqual([{ page: 2 }])

    expect(montar({}).text()).toContain('Todavía no hay deudas')
    const sinResultados = montar({ filtros: { ...FILTROS_INICIALES, q: 'gas' } })
    expect(sinResultados.text()).toContain('Ninguna deuda coincide')
    await sinResultados.get('.vacio button').trigger('click')
    expect(sinResultados.emitted('limpiar')).toHaveLength(1)
  })
})
