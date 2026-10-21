import { describe, expect, it } from 'vitest'
import { motivo, totalesSeleccion, type ItemBandeja } from '@/components/bandeja/modelo'

const item = (cambios: Partial<ItemBandeja>): ItemBandeja =>
  ({
    moneda: 'PEN',
    monto: '10.00',
    saldo: '10.00',
    dias_restantes: 3,
    etiqueta: 'proxima',
    ...cambios,
  }) as ItemBandeja

describe('bandeja (H15)', () => {
  it('dice el motivo de la prioridad (CA06)', () => {
    expect(motivo(item({ etiqueta: 'orden_urgente' })).texto).toBe('Orden urgente del gerente')
    expect(motivo(item({ etiqueta: 'vencida', dias_restantes: -2 })).texto).toBe(
      'Venció hace 2 días',
    )
    expect(motivo(item({ dias_restantes: 1 })).texto).toBe('Vence mañana')
  })

  it('suma lo seleccionado por moneda sin mezclarlas (CA12)', () => {
    expect(totalesSeleccion([item({}), item({ saldo: '5.50' }), item({ moneda: 'USD' })])).toEqual({
      PEN: 15.5,
      USD: 10,
    })
  })
})
