import { describe, expect, it } from 'vitest'
import {
  claveFecha,
  fechasVisibles,
  inicioSemana,
  moverPeriodo,
} from '@/components/calendario/fechas'

describe('fechas del calendario', () => {
  it('muestra solo cuatro semanas cuando febrero cabe exactamente', () => {
    const dias = fechasVisibles(new Date(2027, 1, 18), 'mes')
    expect(dias).toHaveLength(28)
    expect(claveFecha(dias[0]!)).toBe('2027-02-01')
    expect(claveFecha(dias[27]!)).toBe('2027-02-28')
  })

  it('navega de diciembre a enero sin saltar el día 31', () => {
    expect(claveFecha(moverPeriodo(new Date(2026, 11, 31), 'mes', 1))).toBe('2027-01-31')
    expect(claveFecha(moverPeriodo(new Date(2027, 0, 31), 'mes', 1))).toBe('2027-02-28')
  })

  it('empieza la semana en lunes, también al cambiar de año', () => {
    expect(claveFecha(inicioSemana(new Date(2027, 0, 1)))).toBe('2026-12-28')
    expect(fechasVisibles(new Date(2027, 0, 1), 'semana')).toHaveLength(7)
  })
})
