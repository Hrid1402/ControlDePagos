import { http } from './http'
import type { ResultadoDeuda, Ruta, Totales } from '@/components/ruta/modelo'

// Ruta de pagos presenciales (H23): deudas por lugar, inicio en lote y pago declarado.

export async function obtenerRuta(signal?: AbortSignal): Promise<Ruta> {
  const { data } = await http.get<Ruta>('/ruta', { signal })
  return data
}

export interface InicioRuta {
  resultados: ResultadoDeuda[]
  /** Lo que hay que llevar por lo que sí se inició. */
  totales: Totales
}

/** CA02: inicia el pago de lo elegido; cada deuda trae su propio resultado. */
export async function iniciarRuta(deudas: string[]): Promise<InicioRuta> {
  const { data } = await http.post<InicioRuta>('/ruta/iniciar', { deudas })
  return data
}

/** CA03: declara hecho el pago; la deuda sigue por validar hasta que se valide su voucher. */
export async function marcarPagada(id: string): Promise<void> {
  await http.post(`/deudas/${id}/marcar-pagada`)
}
