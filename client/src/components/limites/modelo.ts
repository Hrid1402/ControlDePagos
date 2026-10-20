// Contrato de pantalla de H05 (TASK-21). Los datos llegan en TASK-25 desde GET/PUT /limites y
// GET /solicitudes; aquí solo se definen su forma, su formato y las reglas del formulario.
import { z } from 'zod'

export type Moneda = 'PEN' | 'USD'
export type EstadoSolicitud = 'pendiente' | 'aprobada' | 'rechazada'

/** Límites en soles; null es «sin límite» (CA03). */
export interface Limites {
  por_pago: string | null
  mensual: string | null
}

/** Consumo PEN del mes en Lima: abonos validados de la asistente y reservas en proceso. */
export interface ConsumoMes {
  validado: string
  reservado: string
}

export interface Solicitud {
  id: string
  servicio: string
  asistente: string
  monto: string
  moneda: Moneda
  estado: EstadoSolicitud
  fecha_vencimiento: string
  creado_en: string
  motivo: string | null
  resuelta_por: string | null
  resuelta_en: string | null
}

export const ESTADOS_SOLICITUD: { valor: EstadoSolicitud; etiqueta: string }[] = [
  { valor: 'pendiente', etiqueta: 'Pendientes' },
  { valor: 'aprobada', etiqueta: 'Aprobadas' },
  { valor: 'rechazada', etiqueta: 'Rechazadas' },
]

const formatos = new Map<Moneda, Intl.NumberFormat>()
export function monto(valor: string | number, moneda: Moneda = 'PEN'): string {
  if (!formatos.has(moneda))
    formatos.set(moneda, new Intl.NumberFormat('es-PE', { style: 'currency', currency: moneda }))
  return formatos.get(moneda)!.format(Number(valor))
}

/** «20 de octubre»: sin abreviatura, para que el punto final de la frase no se duplique. */
export function fechaCorta(iso: string): string {
  // Las fechas sin hora son días de Lima: se leen a mediodía para no cambiar de día.
  const fecha = iso.length === 10 ? new Date(`${iso}T12:00:00`) : new Date(iso)
  return fecha.toLocaleDateString('es-PE', {
    timeZone: 'America/Lima',
    day: 'numeric',
    month: 'long',
  })
}

/** Si la deuda vence hoy en Lima, la solicitud se marca urgente (CA09). */
export function venceHoy(fecha: string, hoy = new Date()): boolean {
  return fecha === hoy.toLocaleDateString('en-CA', { timeZone: 'America/Lima' })
}

const MONTO = /^\d{1,10}(\.\d{1,2})?$/
const campoMonto = z
  .string()
  .trim()
  .refine((v) => v === '' || MONTO.test(v), 'Escribe un monto en soles con hasta 2 decimales.')
  .refine((v) => v === '' || Number(v) > 0, 'El monto debe ser mayor que cero.')

/** CA02 y CA03: soles con 2 decimales, vacío es sin límite y por pago no supera al mensual. */
export const esquemaLimites = z
  .object({ por_pago: campoMonto, mensual: campoMonto })
  .refine((v) => !v.por_pago || !v.mensual || Number(v.por_pago) <= Number(v.mensual), {
    message: 'El límite por pago no puede ser mayor que el mensual.',
    path: ['por_pago'],
  })
