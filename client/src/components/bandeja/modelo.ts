// Contrato de pantalla de la bandeja de la asistente (H15, TASK-48). Refleja GET /api/v1/bandeja
// de TASK-49; la pantalla con datos reales es TASK-50.
import type { CategoriaDeuda } from '@/components/deudas/listado'
import type { EstadoDeuda } from '@/components/deudas/estados'
import type { Moneda } from '@/components/deudas/modelo'

export type Pestana = 'por_pagar' | 'por_validar' | 'rechazadas'

export const PESTANAS: { valor: Pestana; etiqueta: string; vacia: string }[] = [
  { valor: 'por_pagar', etiqueta: 'Por pagar', vacia: 'No hay deudas por pagar.' },
  {
    valor: 'por_validar',
    etiqueta: 'Por validar',
    vacia: 'No hay comprobantes esperando validación.',
  },
  { valor: 'rechazadas', etiqueta: 'Rechazadas', vacia: 'Ningún comprobante fue rechazado.' },
]

export type EtiquetaPrioridad =
  'orden_urgente' | 'fijada' | 'vencida' | 'vence_hoy' | 'tarjeta' | 'proxima'

export interface ItemBandeja {
  id: string
  empresa: string | null
  alias: string | null
  codigo_suministro: string
  lugar_pago: string | null
  categoria: CategoriaDeuda
  monto: string | null
  moneda: Moneda
  saldo: string | null
  estado: EstadoDeuda
  fecha_vencimiento: string
  dias_restantes: number
  nivel: number
  etiqueta: EtiquetaPrioridad
  fijada: boolean
  orden_urgente: { id: string; estado: string; plazo: string | null } | null
  en_proceso: { usuario_id: string; rol: string; nombre: string; desde: string | null } | null
  comprobante_estado: string | null
}

export type Contadores = Record<Pestana, number>

/** CA06: el motivo de la prioridad, con su tono e ícono. */
export function motivo(item: ItemBandeja): { texto: string; tono: string; icono: string } {
  const dias = item.dias_restantes
  switch (item.etiqueta) {
    case 'orden_urgente':
      return { texto: 'Orden urgente del gerente', tono: 'urgente', icono: 'pi-bolt' }
    case 'fijada':
      return { texto: 'Fijada', tono: 'fijada', icono: 'pi-thumbtack' }
    case 'vencida':
      return {
        texto: dias === -1 ? 'Venció ayer' : `Venció hace ${-dias} días`,
        tono: 'peligro',
        icono: 'pi-exclamation-circle',
      }
    case 'vence_hoy':
      return { texto: 'Vence hoy', tono: 'peligro', icono: 'pi-clock' }
    case 'tarjeta':
      return { texto: 'Tarjeta de crédito', tono: 'info', icono: 'pi-credit-card' }
    default:
      return {
        texto: dias === 1 ? 'Vence mañana' : `Vence en ${dias} días`,
        tono: dias <= 3 ? 'aviso' : 'neutro',
        icono: 'pi-calendar',
      }
  }
}

export const COMPROBANTES: Record<string, string> = {
  procesando: 'Validando el comprobante',
  en_revision: 'El gerente revisa el comprobante',
  por_confirmar: 'Comprobante por confirmar',
  rechazado: 'Comprobante rechazado: adjunta otro',
}

/** Totales por moneda de lo seleccionado, sin sumar soles con dólares. */
export function totalesSeleccion(items: ItemBandeja[]): Partial<Record<Moneda, number>> {
  const totales: Partial<Record<Moneda, number>> = {}
  for (const item of items) {
    const valor = Number(item.saldo ?? item.monto ?? 0)
    totales[item.moneda] = (totales[item.moneda] ?? 0) + valor
  }
  return totales
}

/** La pestaña y la categoría viven en la URL: se conservan al volver del detalle. */
export function consultaDeQuery(query: Record<string, unknown>): {
  pestana: Pestana
  categoria: string
} {
  const pestana = PESTANAS.find((p) => p.valor === query.pestana)?.valor ?? 'por_pagar'
  const categoria = typeof query.categoria === 'string' ? query.categoria : ''
  return { pestana, categoria }
}

/** Solo lo que difiere de la vista inicial, para que la URL de inicio quede limpia. */
export function queryDeConsulta(consulta: {
  pestana: Pestana
  categoria: string
}): Record<string, string> {
  const query: Record<string, string> = {}
  if (consulta.pestana !== 'por_pagar') query.pestana = consulta.pestana
  if (consulta.categoria) query.categoria = consulta.categoria
  return query
}
