// Contrato de pantalla de la ruta de pagos (H23, TASK-78). Refleja GET /api/v1/ruta y
// POST /api/v1/ruta/iniciar de TASK-79; la pantalla con datos reales es TASK-80.
import type { CategoriaDeuda } from '@/components/deudas/listado'
import { importe, MONEDAS, type Moneda } from '@/components/deudas/modelo'
import { LUGARES_PAGO } from '@/components/servicios/modelo'

export interface ItemRuta {
  id: string
  empresa: string | null
  alias: string | null
  codigo_suministro: string
  categoria: CategoriaDeuda
  monto: string
  saldo: string
  moneda: Moneda
  estado: string
  fecha_vencimiento: string
  /** La persona ya la tiene en proceso: está en su ruta. */
  en_ruta: boolean
  /** Declaró el pago; sigue por validar hasta que se valide el comprobante. */
  pago_realizado: boolean
  pago_realizado_en: string | null
  comprobante_estado: string | null
}

export type Totales = Record<Moneda, string>

export interface GrupoRuta {
  /** null: el servicio no tiene lugar de pago registrado. */
  lugar: string | null
  items: ItemRuta[]
  totales: Totales
}

export interface Ruta {
  grupos: GrupoRuta[]
  totales: Totales
}

export type ResultadoLote = 'iniciada' | 'requiere_aprobacion' | 'conflicto'

export interface ResultadoDeuda {
  deuda_id: string
  resultado: ResultadoLote
  codigo: string | null
  mensaje: string | null
  repetido: boolean
}

/** Dónde se paga el grupo, con su ícono. */
export function lugarDe(lugar: string | null): { titulo: string; icono: string } {
  const encontrado = LUGARES_PAGO.find((l) => l.valor === lugar)
  if (!encontrado) return { titulo: 'Sin lugar registrado', icono: 'pi-question-circle' }
  return { titulo: encontrado.etiqueta, icono: encontrado.icono }
}

/** En qué punto está cada deuda de la ruta. Declarada no es validada (TASK-80). */
export type Paso =
  'disponible' | 'espera_aprobacion' | 'por_pagar' | 'declarada' | 'validando' | 'rechazado'

export function pasoDe(item: ItemRuta): Paso {
  if (item.estado === 'esperando_aprobacion') return 'espera_aprobacion'
  if (!item.en_ruta) return 'disponible'
  if (item.comprobante_estado === 'rechazado') return 'rechazado'
  if (item.comprobante_estado) return 'validando'
  return item.pago_realizado ? 'declarada' : 'por_pagar'
}

export const PASOS: Record<Paso, { texto: string; icono: string } | null> = {
  disponible: null,
  espera_aprobacion: { texto: 'Espera la aprobación del gerente', icono: 'pi-hourglass' },
  por_pagar: { texto: 'En tu ruta', icono: 'pi-directions' },
  declarada: { texto: 'Pagada · falta el comprobante', icono: 'pi-check' },
  validando: { texto: 'Comprobante en validación', icono: 'pi-spinner' },
  rechazado: { texto: 'Comprobante rechazado: adjunta otro', icono: 'pi-times-circle' },
}

/** Lo que hay que llevar: soles y dólares por separado y sin convertir. */
export function totalDe(items: ItemRuta[]): Partial<Record<Moneda, number>> {
  const totales: Partial<Record<Moneda, number>> = {}
  for (const item of items) totales[item.moneda] = (totales[item.moneda] ?? 0) + Number(item.saldo)
  return totales
}

/** «S/ 147.50 + USD 20.00», o «S/ 0.00» si no hay nada. */
export function textoTotal(items: ItemRuta[]): string {
  const totales = totalDe(items)
  const partes = MONEDAS.flatMap((m) => {
    const valor = totales[m.valor]
    return valor ? [importe(valor, m.valor)] : []
  })
  return partes.join(' + ') || importe(0, 'PEN')
}

/** Las de su ruta que falta pagar, las declaradas y las que necesitan su comprobante (CA04). */
export function avance(grupos: GrupoRuta[]) {
  const enRuta = grupos.flatMap((g) => g.items).filter((i) => i.en_ruta)
  const porPagar = enRuta.filter((i) => pasoDe(i) === 'por_pagar')
  const sinComprobante = enRuta.filter((i) => ['declarada', 'rechazado'].includes(pasoDe(i)))
  return {
    enRuta,
    porPagar,
    sinComprobante,
    terminada: enRuta.length > 0 && porPagar.length === 0,
  }
}
