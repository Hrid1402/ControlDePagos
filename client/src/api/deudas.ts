import { http } from './http'
import type { ComentarioDeuda, DetalleDeuda } from '@/components/deudas/detalle'
import {
  parametrosApi,
  type FiltrosDeudas,
  type ItemDeuda,
  type Totales,
} from '@/components/deudas/listado'
import type { DatosDeuda } from '@/components/deudas/modelo'

// Deudas del gerente: listado (H36), registro (H11), detalle, comentarios e inicio o cancelación
// del pago presencial (H17).

export interface PaginaDeudas {
  items: ItemDeuda[]
  total: number
  page: number
  totales: Totales
}

export async function listarDeudas(
  filtros: FiltrosDeudas,
  signal?: AbortSignal,
): Promise<PaginaDeudas> {
  const { data } = await http.get<PaginaDeudas>('/deudas', {
    params: parametrosApi(filtros),
    // estado se repite (estado=a&estado=b), como lo lee FastAPI.
    paramsSerializer: { indexes: null },
    signal,
  })
  return data
}

/** Registro manual de una deuda (H11 CA01): monto, vencimiento y opcionales del recibo. */
export async function registrarDeuda(datos: DatosDeuda): Promise<{ id: string }> {
  const { data } = await http.post<{ id: string }>('/deudas', {
    servicio_id: datos.servicio_id,
    monto: datos.monto,
    moneda: datos.moneda,
    fecha_vencimiento: datos.fecha_vencimiento,
    periodo: datos.periodo,
    numero_recibo: datos.numero_recibo,
    fecha_emision: datos.fecha_emision,
    fecha_corte: datos.fecha_corte,
    pago_minimo: datos.pago_minimo,
  })
  return data
}

/** Préstamo con su cronograma (CA07): una deuda por cuota. */
export async function crearPrestamo(datos: DatosDeuda): Promise<{ id: string }> {
  const { data } = await http.post<{ id: string }>('/prestamos', {
    servicio_id: datos.servicio_id,
    monto_total: datos.monto_total,
    cuotas_total: datos.cuotas_total,
    fecha_primera_cuota: datos.fecha_primera_cuota,
    moneda: datos.moneda,
  })
  return data
}

export interface Recurrencia {
  monto: string | null
  moneda: string
  dia_emision: number | null
  dia_vencimiento: number
  activa: boolean
}

/** La deuda se repite cada mes (CA04 y CA05). */
export async function configurarRecurrencia(servicioId: string, datos: Recurrencia): Promise<void> {
  await http.put(`/servicios/${servicioId}/recurrencia`, datos)
}

export async function subirRecibo(deudaId: string, archivo: File): Promise<DetalleDeuda> {
  const datos = new FormData()
  datos.append('archivo', archivo)
  const { data } = await http.post<DetalleDeuda>(`/deudas/${deudaId}/recibo`, datos)
  return data
}

export interface CambiosDeuda {
  monto?: string
  fecha_vencimiento?: string
  fecha_emision?: string
  numero_recibo?: string
  pago_minimo?: string
}

export async function editarDeuda(id: string, cambios: CambiosDeuda): Promise<DetalleDeuda> {
  const { data } = await http.put<DetalleDeuda>(`/deudas/${id}`, cambios)
  return data
}

export async function anularDeuda(id: string, motivo: string | null): Promise<DetalleDeuda> {
  const { data } = await http.post<DetalleDeuda>(`/deudas/${id}/anular`, motivo ? { motivo } : {})
  return data
}

export async function obtenerDeuda(id: string, signal?: AbortSignal): Promise<DetalleDeuda> {
  const { data } = await http.get<DetalleDeuda>(`/deudas/${id}`, { signal })
  return data
}

export async function listarComentarios(id: string): Promise<ComentarioDeuda[]> {
  const { data } = await http.get<ComentarioDeuda[]>(`/deudas/${id}/comentarios`)
  return data
}

export async function comentarDeuda(id: string, texto: string): Promise<ComentarioDeuda> {
  const { data } = await http.post<ComentarioDeuda>(`/deudas/${id}/comentarios`, { texto })
  return data
}

export interface InicioPago {
  resultado: 'iniciado' | 'requiere_aprobacion'
  repetido: boolean
}

export async function iniciarPago(id: string): Promise<InicioPago> {
  const { data } = await http.post<InicioPago>(`/deudas/${id}/iniciar-pago`)
  return data
}

export async function cancelarInicio(id: string, motivo: string | null): Promise<void> {
  await http.post(`/deudas/${id}/cancelar-inicio`, motivo ? { motivo } : {})
}
