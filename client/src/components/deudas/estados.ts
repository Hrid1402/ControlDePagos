// Estados de una deuda (ck_deuda_estado) dichos como los lee quien paga. Lo comparten la lista
// (H36), el detalle (H17) y la bandeja (H15): un estado tiene el mismo nombre, tono e ícono en
// todas las pantallas. El color solo refuerza; el estado siempre se lee en el texto (CA06).

export type EstadoDeuda =
  | 'esperando_recibo'
  | 'pendiente'
  | 'esperando_aprobacion'
  | 'en_proceso'
  | 'por_validar'
  | 'pagada_parcial'
  | 'pagada'
  | 'con_problema'
  | 'anulada'

export type Tono = 'aviso' | 'peligro' | 'exito' | 'info' | 'proceso' | 'neutro'

export interface DescripcionEstado {
  etiqueta: string
  tono: Tono
  icono: string
  /** Qué significa y qué sigue, para el detalle y las ayudas. */
  explica: string
}

export const ESTADOS: Record<EstadoDeuda, DescripcionEstado> = {
  esperando_recibo: {
    etiqueta: 'Esperando recibo',
    tono: 'info',
    icono: 'pi-hourglass',
    explica: 'Todavía no llega el recibo del mes: se paga cuando se confirme el monto.',
  },
  pendiente: {
    etiqueta: 'Pendiente',
    tono: 'aviso',
    icono: 'pi-clock',
    explica: 'Lista para pagarse.',
  },
  esperando_aprobacion: {
    etiqueta: 'Esperando aprobación',
    tono: 'proceso',
    icono: 'pi-user-edit',
    explica: 'Supera el límite de la asistente: el gerente debe aprobar el pago.',
  },
  en_proceso: {
    etiqueta: 'En proceso',
    tono: 'proceso',
    icono: 'pi-spinner',
    explica: 'Alguien está pagándola; falta adjuntar el comprobante.',
  },
  por_validar: {
    etiqueta: 'Por validar',
    tono: 'info',
    icono: 'pi-file-check',
    explica: 'Su comprobante se está validando.',
  },
  pagada_parcial: {
    etiqueta: 'Pagada en parte',
    tono: 'aviso',
    icono: 'pi-chart-pie',
    explica: 'Tiene abonos validados y aún queda saldo por pagar.',
  },
  pagada: {
    etiqueta: 'Pagada',
    tono: 'exito',
    icono: 'pi-check-circle',
    explica: 'Pagada y con su comprobante validado.',
  },
  con_problema: {
    etiqueta: 'Con problema',
    tono: 'peligro',
    icono: 'pi-exclamation-triangle',
    explica: 'No se pudo pagar: el gerente decide cómo seguir.',
  },
  anulada: {
    etiqueta: 'Anulada',
    tono: 'neutro',
    icono: 'pi-ban',
    explica: 'Ya no se cobra. Se conserva solo como historial.',
  },
}

export function estadoDe(valor: string): DescripcionEstado {
  return ESTADOS[valor as EstadoDeuda] ?? ESTADOS.pendiente
}

/** Días entre dos fechas AAAA-MM-DD, sin depender de la zona del navegador. */
export function diasEntre(desde: string, hasta: string): number {
  const dia = (fecha: string) =>
    Date.UTC(...(fecha.split('-').map(Number) as [number, number, number]))
  return Math.round((dia(hasta) - dia(desde)) / 86_400_000)
}

/** «Vence hoy», «Vence en 3 días», «Venció hace 2 días». cerrada: pagada o anulada, sin urgencia. */
export function plazo(
  fecha: string,
  hoy: string,
  cerrada = false,
): { texto: string; tono: 'peligro' | 'aviso' | 'neutro' } {
  const dias = diasEntre(hoy, fecha)
  if (cerrada) return { texto: '', tono: 'neutro' }
  if (dias < 0)
    return { texto: dias === -1 ? 'Venció ayer' : `Venció hace ${-dias} días`, tono: 'peligro' }
  if (dias === 0) return { texto: 'Vence hoy', tono: 'peligro' }
  if (dias === 1) return { texto: 'Vence mañana', tono: 'aviso' }
  if (dias <= 7) return { texto: `Vence en ${dias} días`, tono: 'aviso' }
  return { texto: `Vence en ${dias} días`, tono: 'neutro' }
}

/** «20 oct.», o «20 oct. 2025» si no es del año de hoy. */
export function fechaCorta(fecha: string, hoy: string): string {
  const opciones: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short' }
  if (fecha.slice(0, 4) !== hoy.slice(0, 4)) opciones.year = 'numeric'
  return new Date(`${fecha}T12:00:00`).toLocaleDateString('es-PE', opciones)
}
