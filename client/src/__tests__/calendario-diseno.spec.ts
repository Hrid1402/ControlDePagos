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

afterEach(() => vi.unstubAllGlobals())

describe('diseño del calendario', () => {
  it('inicia en lista en celular y permite abrir una deuda desde el detalle', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true }))
    const vista = mount(CalendarioSuperficie, { props: { dias: [dia] } })
    await nextTick()
    expect(vista.get('button[aria-pressed="true"].activa').text()).toBe('Lista')
    await vista.get('button.fila-fecha').trigger('click')
    expect(vista.text()).toContain('Servicio de agua')
    expect(vista.text()).toContain('S/ 120.50')
    await vista.get('button.deuda').trigger('click')
    expect(vista.emitted('abrirDeuda')?.[0]).toEqual(['deuda-1'])
  })

  it('muestra el error con una acción para reintentar', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false }))
    const vista = mount(CalendarioSuperficie, { props: { estadoPantalla: 'error' } })
    expect(vista.get('[role="alert"]').text()).toContain('No pudimos cargar el calendario')
    await vista.get('[role="alert"] button').trigger('click')
    expect(vista.emitted('reintentar')).toHaveLength(1)
  })
})
