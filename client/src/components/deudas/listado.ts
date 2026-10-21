// Contrato de pantalla de la lista de deudas (H36, TASK-43). Refleja GET /api/v1/deudas de
// TASK-45; la pantalla con datos reales (TASK-46) traduce estos filtros a la URL y a la API.
import type { Moneda } from './modelo'
import type { EstadoDeuda } from './estados'

export interface CategoriaDeuda {
  id: string
  nombre: string
  color: string
  icono: string
  tipo: string
}

export interface ItemDeuda {
  id: string
  servicio_id: string
  empresa: string
  alias: string | null
  codigo_suministro: string
  categoria: CategoriaDeuda
  /** AAAA-MM */
  periodo: string
  /** null: esperando recibo; su estimación va en monto_proyectado. */
  monto: string | null
  moneda: Moneda
  pagado: string
  saldo: string | null
  monto_proyectado: string | null
  fecha_vencimiento: string
  vencida: boolean
  estado: EstadoDeuda
  numero_recibo: string | null
}

export interface TotalesMoneda {
  cantidad: number
  monto: string
  pagado: string
  saldo: string
  sin_monto: number
  proyectado: string
  sin_estimacion: number
}

export type Totales = Record<Moneda, TotalesMoneda>

/** Atajos de estado de la lista. Cada uno se traduce a los parámetros estado/vencida de la API. */
export type Vista =
  'activas' | 'por_pagar' | 'vencidas' | 'en_curso' | 'esperando' | 'pagadas' | 'anuladas'

export const VISTAS: {
  valor: Vista
  etiqueta: string
  estados: EstadoDeuda[]
  vencida?: boolean
}[] = [
  // Sin estado, la API trae todas menos las anuladas.
  { valor: 'activas', etiqueta: 'Todas', estados: [] },
  {
    valor: 'por_pagar',
    etiqueta: 'Por pagar',
    estados: ['pendiente', 'pagada_parcial', 'esperando_aprobacion', 'con_problema'],
  },
  { valor: 'vencidas', etiqueta: 'Vencidas', estados: [], vencida: true },
  { valor: 'en_curso', etiqueta: 'En curso', estados: ['en_proceso', 'por_validar'] },
  { valor: 'esperando', etiqueta: 'Esperando recibo', estados: ['esperando_recibo'] },
  { valor: 'pagadas', etiqueta: 'Pagadas', estados: ['pagada'] },
  { valor: 'anuladas', etiqueta: 'Anuladas', estados: ['anulada'] },
]

export type Orden = 'vencimiento' | '-vencimiento' | '-monto' | 'monto' | 'estado'

export const ORDENES: { valor: Orden; etiqueta: string }[] = [
  { valor: 'vencimiento', etiqueta: 'Vence primero' },
  { valor: '-vencimiento', etiqueta: 'Vence al final' },
  { valor: '-monto', etiqueta: 'Monto mayor' },
  { valor: 'monto', etiqueta: 'Monto menor' },
  { valor: 'estado', etiqueta: 'Estado' },
]

export interface FiltrosDeudas {
  q: string
  vista: Vista
  categoria: string
  /** AAAA-MM o vacío. */
  mes: string
  orden: Orden
  page: number
}

export const FILTROS_INICIALES: FiltrosDeudas = {
  q: '',
  vista: 'activas',
  categoria: '',
  mes: '',
  orden: 'vencimiento',
  page: 1,
}

export const TAMANO_PAGINA = 20

/** Parámetros de GET /deudas para estos filtros. */
export function parametrosApi(f: FiltrosDeudas): Record<string, string | string[] | number> {
  const vista = VISTAS.find((v) => v.valor === f.vista) ?? VISTAS[0]!
  const parametros: Record<string, string | string[] | number> = {
    orden: f.orden,
    page: f.page,
    size: TAMANO_PAGINA,
  }
  if (f.q) parametros.q = f.q
  if (vista.estados.length) parametros.estado = vista.estados
  if (vista.vencida) parametros.vencida = 'true'
  if (f.categoria) parametros.categoria = f.categoria
  if (f.mes) parametros.mes = f.mes
  return parametros
}

export const hayFiltros = (f: FiltrosDeudas) =>
  !!f.q || f.vista !== 'activas' || !!f.categoria || !!f.mes

/** «Hidrandina» o «Luz de la casa» con la empresa debajo. */
export const nombreDeuda = (d: Pick<ItemDeuda, 'alias' | 'empresa'>) => d.alias || d.empresa
