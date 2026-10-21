// Contrato de pantalla del formulario de deuda de H11 (TASK-36). El tipo de la categoría del
// servicio decide qué se pide: monto y vencimiento (servicio variable y monto fijo), corte, pago
// mínimo y total (tarjeta), o total, cuotas y primera fecha (préstamo). Los datos se conectan en
// TASK-41 con POST /deudas, /recurrencias y /prestamos.
import { z } from 'zod'
import type { TipoCategoria } from '@/components/categorias/modelo'
import type { Servicio } from '@/components/servicios/modelo'

export type Moneda = 'PEN' | 'USD'

export const MONEDAS: { valor: Moneda; etiqueta: string; simbolo: string }[] = [
  { valor: 'PEN', etiqueta: 'Soles', simbolo: 'S/' },
  { valor: 'USD', etiqueta: 'Dólares', simbolo: 'US$' },
]
export const simbolo = (moneda: unknown) => MONEDAS.find((m) => m.valor === moneda)?.simbolo ?? 'S/'

/** Qué registra cada tipo, dicho como lo ve quien llena el formulario. */
export const VARIANTES: Record<TipoCategoria, { titulo: string; explica: string; icono: string }> =
  {
    servicio_variable: {
      titulo: 'Recibo del mes',
      explica: 'El monto cambia cada mes: escribe el del recibo que te llegó.',
      icono: 'pi-receipt',
    },
    monto_fijo: {
      titulo: 'Pago fijo',
      explica: 'Se paga lo mismo cada mes. Puedes dejarlo programado.',
      icono: 'pi-sync',
    },
    tarjeta: {
      titulo: 'Estado de cuenta',
      explica: 'Registra el corte, el pago mínimo y el total del estado de cuenta.',
      icono: 'pi-credit-card',
    },
    prestamo: {
      titulo: 'Préstamo en cuotas',
      explica: 'Con el total, las cuotas y la primera fecha armamos el cronograma.',
      icono: 'pi-calendar-clock',
    },
  }

/** El periodo es el mes que cubre la deuda; sin indicarlo, la API usa el del vencimiento (CA01). */
export const periodoDe = (fecha: string) => fecha.slice(0, 7)

/** «octubre de 2026». */
export function nombrePeriodo(periodo: string): string {
  return new Date(`${periodo}-15T12:00:00`).toLocaleDateString('es-PE', {
    month: 'long',
    year: 'numeric',
  })
}

/** «20 de octubre de 2026». Las fechas sin hora son días de Lima: se leen a mediodía. */
export function fechaLarga(fecha: string): string {
  return new Date(`${fecha}T12:00:00`).toLocaleDateString('es-PE', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

export const hoyEnLima = (ahora = new Date()) =>
  ahora.toLocaleDateString('en-CA', { timeZone: 'America/Lima' })

/** CA02: se puede registrar ya vencida; solo se advierte. */
export const estaVencida = (fecha: unknown, hoy: string) =>
  typeof fecha === 'string' && fecha !== '' && fecha < hoy

const formatos = new Map<Moneda, Intl.NumberFormat>()
export function importe(valor: string | number, moneda: Moneda = 'PEN'): string {
  if (!formatos.has(moneda))
    formatos.set(moneda, new Intl.NumberFormat('es-PE', { style: 'currency', currency: moneda }))
  return formatos.get(moneda)!.format(Number(valor))
}

export interface Cuota {
  numero: number
  fecha: string
  monto: string
}

/** Mismo día cada mes; si el mes no lo tiene (31 en febrero), el último día de ese mes. */
export function sumarMeses(fecha: string, meses: number): string {
  const [anio, mes, dia] = fecha.split('-').map(Number) as [number, number, number]
  const destino = new Date(Date.UTC(anio, mes - 1 + meses, 1))
  const ultimo = new Date(
    Date.UTC(destino.getUTCFullYear(), destino.getUTCMonth() + 1, 0),
  ).getUTCDate()
  destino.setUTCDate(Math.min(dia, ultimo))
  return destino.toISOString().slice(0, 10)
}

/**
 * CA07: cuotas iguales en céntimos; la última absorbe la diferencia para que la suma sea exacta.
 * Devuelve [] si los datos aún no alcanzan para calcularlo.
 */
export function cronograma(total: unknown, cuotas: unknown, primera: unknown): Cuota[] {
  const centimos = Math.round(Number(total) * 100)
  const n = Number(cuotas)
  if (!(centimos > 0) || !Number.isInteger(n) || n < 1 || n > MAX_CUOTAS) return []
  if (typeof primera !== 'string' || !FECHA.test(primera)) return []
  const base = Math.floor(centimos / n)
  return Array.from({ length: n }, (_, i) => ({
    numero: i + 1,
    fecha: sumarMeses(primera, i),
    monto: ((i === n - 1 ? centimos - base * (n - 1) : base) / 100).toFixed(2),
  }))
}

export const MAX_CUOTAS = 360
const FECHA = /^\d{4}-\d{2}-\d{2}$/
const MONTO = /^\d{1,10}(\.\d{1,2})?$/
const PERIODO = /^[1-9]\d{3}-(0[1-9]|1[0-2])$/

export interface DatosDeuda {
  servicio_id: string
  tipo: TipoCategoria
  moneda: Moneda
  /** Monto, vencimiento y recibo: todo menos préstamo. En tarjeta, monto es el pago total. */
  monto: string | null
  fecha_vencimiento: string | null
  fecha_emision: string | null
  periodo: string | null
  numero_recibo: string | null
  recibo: File | null
  /** Servicio variable y monto fijo: también los meses siguientes (CA04 y CA05). */
  repetir: boolean
  /** Tarjeta (CA06). */
  fecha_corte: string | null
  pago_minimo: string | null
  /** Préstamo (CA07). */
  monto_total: string | null
  cuotas_total: number | null
  fecha_primera_cuota: string | null
}

// Los mismos que acepta el almacenamiento privado del server (TASK-84).
export const RECIBO_TIPOS = ['application/pdf', 'image/jpeg', 'image/png']
export const RECIBO_MAXIMO = 10 * 1024 * 1024

const texto = (valor: unknown) => (typeof valor === 'string' ? valor.trim() : '')

/** CA01, CA02 y CA06 a CA09 según el tipo del servicio elegido. */
export function esquemaDeuda(servicios: Servicio[]) {
  return z
    .object({
      servicio_id: z.string().min(1, 'Elige el servicio.'),
      moneda: z.enum(['PEN', 'USD']),
      monto: z.string().trim(),
      fecha_vencimiento: z.string(),
      fecha_emision: z.string(),
      periodo: z.string().trim(),
      numero_recibo: z.string().trim().max(60, 'Usa como máximo 60 caracteres.'),
      recibo: z.custom<File | null>(),
      repetir: z.boolean(),
      fecha_corte: z.string(),
      pago_minimo: z.string().trim(),
      monto_total: z.string().trim(),
      cuotas_total: z.string().trim(),
      fecha_primera_cuota: z.string(),
    })
    .superRefine((v, ctx) => {
      const tipo = servicios.find((s) => s.id === v.servicio_id)?.categoria.tipo
      if (!tipo) return
      const falta = (campo: string, message: string) =>
        ctx.addIssue({ code: 'custom', path: [campo], message })
      const montoValido = (campo: string, valor: string, nombre: string) => {
        if (!valor) return falta(campo, `Escribe ${nombre}.`)
        if (!MONTO.test(valor) || !(Number(valor) > 0))
          return falta(campo, 'Escribe un monto mayor que cero, con hasta 2 decimales.')
        return true
      }

      if (tipo === 'prestamo') {
        montoValido('monto_total', v.monto_total, 'el total del préstamo')
        const n = Number(v.cuotas_total)
        if (!v.cuotas_total) falta('cuotas_total', 'Escribe el número de cuotas.')
        else if (!Number.isInteger(n) || n < 1 || n > MAX_CUOTAS)
          falta('cuotas_total', `Usa un número entero de 1 a ${MAX_CUOTAS}.`)
        if (!v.fecha_primera_cuota) falta('fecha_primera_cuota', 'Elige la fecha de la primera.')
        return
      }

      if (tipo === 'tarjeta') {
        if (!v.fecha_corte) falta('fecha_corte', 'Elige la fecha de corte.')
        if (!v.fecha_vencimiento) falta('fecha_vencimiento', 'Elige la fecha de pago.')
        else if (v.fecha_corte && v.fecha_vencimiento < v.fecha_corte)
          falta('fecha_vencimiento', 'La fecha de pago es posterior al corte.')
        const total = montoValido('monto', v.monto, 'el pago total')
        if (v.pago_minimo && montoValido('pago_minimo', v.pago_minimo, 'el pago mínimo')) {
          if (total === true && Number(v.pago_minimo) > Number(v.monto))
            falta('pago_minimo', 'El pago mínimo no puede superar al total.')
        }
      } else {
        montoValido('monto', v.monto, 'el monto')
        if (!v.fecha_vencimiento) falta('fecha_vencimiento', 'Elige la fecha de vencimiento.')
        if (v.fecha_emision && v.fecha_vencimiento && v.fecha_emision > v.fecha_vencimiento)
          falta('fecha_emision', 'La emisión no puede ser posterior al vencimiento.')
      }
      if (v.periodo && !PERIODO.test(v.periodo)) falta('periodo', 'Elige un mes válido.')
      if (v.recibo && !RECIBO_TIPOS.includes(v.recibo.type))
        falta('recibo', 'Adjunta un PDF o una imagen JPG o PNG.')
      else if (v.recibo && v.recibo.size > RECIBO_MAXIMO)
        falta('recibo', 'El archivo pesa más de 10 MB.')
    })
}

export function valoresIniciales(servicioId = '', moneda: Moneda = 'PEN') {
  return {
    servicio_id: servicioId,
    moneda,
    monto: '',
    fecha_vencimiento: '',
    fecha_emision: '',
    periodo: '',
    numero_recibo: '',
    recibo: null as File | null,
    repetir: false,
    fecha_corte: '',
    pago_minimo: '',
    monto_total: '',
    cuotas_total: '',
    fecha_primera_cuota: '',
  }
}

/** Solo viaja lo que pide el tipo; lo escrito en otra variante antes de cambiar se descarta. */
export function aDatos(valores: Record<string, unknown>, tipo: TipoCategoria): DatosDeuda {
  const opcional = (campo: string) => texto(valores[campo]) || null
  const prestamo = tipo === 'prestamo'
  const tarjeta = tipo === 'tarjeta'
  return {
    servicio_id: texto(valores.servicio_id),
    tipo,
    moneda: valores.moneda === 'USD' ? 'USD' : 'PEN',
    monto: prestamo ? null : opcional('monto'),
    fecha_vencimiento: prestamo ? null : opcional('fecha_vencimiento'),
    fecha_emision: prestamo || tarjeta ? null : opcional('fecha_emision'),
    periodo: prestamo ? null : opcional('periodo'),
    numero_recibo: prestamo ? null : opcional('numero_recibo'),
    recibo: prestamo ? null : ((valores.recibo as File | null) ?? null),
    repetir: !prestamo && !tarjeta && valores.repetir === true,
    fecha_corte: tarjeta ? opcional('fecha_corte') : null,
    pago_minimo: tarjeta ? opcional('pago_minimo') : null,
    monto_total: prestamo ? opcional('monto_total') : null,
    cuotas_total: prestamo ? Number(valores.cuotas_total) : null,
    fecha_primera_cuota: prestamo ? opcional('fecha_primera_cuota') : null,
  }
}

/** Lo que devuelve el 409 DUPLICADO de POST /deudas (CA03). */
export interface DeudaExistente {
  id: string
  periodo: string
  estado: string
  monto: string | null
  moneda: Moneda
  fecha_vencimiento: string
}
