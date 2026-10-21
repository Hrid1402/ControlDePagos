import { http } from './http'

// Comprobantes de pago (H24): subida con el reparto entre deudas y consulta con enlace firmado.

export interface Comprobante {
  id: string
  estado: string
  motivo_codigo: string | null
  observacion: string | null
  archivo_enlace: string | null
}

/** Sube el archivo para una deuda; sin monto se aplica todo su saldo por cubrir. */
export async function subirComprobante(deudaId: string, archivo: File): Promise<Comprobante> {
  const datos = new FormData()
  datos.append('archivo', archivo)
  datos.append('deudas', JSON.stringify([{ deuda_id: deudaId }]))
  const { data } = await http.post<Comprobante>('/comprobantes', datos)
  return data
}

export async function obtenerComprobante(id: string): Promise<Comprobante> {
  const { data } = await http.get<Comprobante>(`/comprobantes/${id}`)
  return data
}
