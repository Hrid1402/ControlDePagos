import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import CalendarioSuperficie from '@/components/calendario/CalendarioSuperficie.vue'
import type { DiaCalendario } from '@/components/calendario/modelo'

const dia: DiaCalendario = {
  fecha: '2026-10-25',
  deudas: [
    {
      id: 'deuda-1',
      servicio_id: 'servicio-1',
      nombre: 'Servicio de agua',
      estado: 'pendiente',
      monto: '120.50',
      monto_proyectado: null,
      moneda: 'PEN',
      categoria_id: 'categoria-1',
      fecha_vencimiento: '2026-10-25',
    },
  ],
  totales_confirmados: { PEN: '120.50' },
  totales_proyectados: {},
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('diseño del calendario', () => {
  it('inicia en lista en celular y permite abrir una deuda desde el detalle', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true }))
    const vista = mount(CalendarioSuperficie, { props: { dias: [dia] } })
    await nextTick()
    expect(vista.get('button[aria-pressed="true"].activa').text()).toBe('Lista')
    expect(vista.find('.fc-listMonth-view').exists()).toBe(true)
    expect(vista.text()).toContain('Servicio de agua')
    await vista.get('.fc-list-event').trigger('click')
    expect(vista.emitted('abrirDeuda')?.[0]).toEqual(['deuda-1'])
  })

  it('muestra el error con una acción para reintentar', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false }))
    const vista = mount(CalendarioSuperficie, { props: { estadoPantalla: 'error' } })
    expect(vista.get('[role="alert"]').text()).toContain('No pudimos cargar el calendario')
    await vista.get('[role="alert"] button').trigger('click')
    expect(vista.emitted('reintentar')).toHaveLength(1)
  })

  it('usa vistas reales y consulta el rango visible al navegar de diciembre a enero', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false }))
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 11, 15))
    const vista = mount(CalendarioSuperficie)
    await nextTick()
    expect(vista.find('.fc-dayGridMonth-view').exists()).toBe(true)
    expect(vista.emitted('consultar')?.length).toBeGreaterThan(0)
    const consultasIniciales = vista.emitted('consultar')?.length
    await vista.setProps({ dias: [dia] })
    expect(vista.emitted('consultar')?.length).toBe(consultasIniciales)
    await vista.get('button[aria-label="Periodo siguiente"]').trigger('click')
    expect(vista.emitted('consultar')?.slice(-1)[0]?.[0]).toMatchObject({
      desde: '2026-12-28',
      hasta: '2027-01-31',
    })
    await vista.get('.vistas button:nth-child(2)').trigger('click')
    expect(vista.find('.fc-dayGridWeek-view').exists()).toBe(true)
    await vista.get('.vistas button:nth-child(3)').trigger('click')
    expect(vista.find('.fc-listMonth-view').exists()).toBe(true)
    await vista.get('#calendario-estado').setValue('pagada')
    expect(vista.emitted('consultar')?.slice(-1)[0]?.[0]).toMatchObject({ estado: 'pagada' })
  })
})
