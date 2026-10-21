import { http } from './http'
import type { ComentarioDeuda, DetalleDeuda } from '@/components/deudas/detalle'

// Deudas del gerente (H17): detalle, comentarios e inicio o cancelación del pago presencial.

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
