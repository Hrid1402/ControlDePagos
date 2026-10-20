export type VistaCalendario = 'mes' | 'semana' | 'lista'

export interface VencimientoCalendario {
  id: string
  servicio_id: string
  nombre: string
  estado: string
  monto: string | null
  monto_proyectado: string | null
  moneda: 'PEN' | 'USD'
  categoria_id: string
  fecha_vencimiento: string
}

export interface DiaCalendario {
  fecha: string
  deudas: VencimientoCalendario[]
  totales_confirmados: Partial<Record<'PEN' | 'USD', string>>
  totales_proyectados: Partial<Record<'PEN' | 'USD', string>>
}

export interface CategoriaCalendario {
  id: string
  nombre: string
}
