import axios, { type AxiosInstance } from 'axios'
import { useSesionStore } from '@/stores/sesion'
import type { ErrorApi } from '@/types/api'

export function normalizarError(error: unknown): ErrorApi {
  if (!axios.isAxiosError(error)) {
    return { status: 0, code: 'ERROR_INTERNO', detail: 'Ocurrió un error inesperado.', field: null }
  }
  if (!error.response) {
    const tiempo = error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT'
    const cancelada = axios.isCancel(error)
    return {
      status: 0,
      code: cancelada ? 'CANCELADA' : tiempo ? 'TIEMPO_AGOTADO' : 'SIN_CONEXION',
      detail: cancelada
        ? 'La solicitud se canceló.'
        : tiempo
          ? 'El servidor tardó demasiado. Revisa el resultado antes de intentar de nuevo.'
          : 'No hay conexión con el servidor. Conservamos lo escrito para que puedas reintentar.',
      field: null,
    }
  }
  const datos = error.response.data
  return {
    status: error.response.status,
    code: typeof datos?.code === 'string' ? datos.code : 'ERROR_HTTP',
    detail:
      typeof datos?.detail === 'string'
        ? datos.detail
        : 'Ocurrió un error inesperado. Intenta de nuevo.',
    field: typeof datos?.field === 'string' ? datos.field : null,
  }
}

export function crearHttp(opciones: {
  obtenerToken: () => string | null
  alNoAutenticado: (error: ErrorApi) => void
}): AxiosInstance {
  const instancia = axios.create({
    baseURL: import.meta.env.VITE_API_URL || '/api/v1',
    timeout: 30000,
  })
  instancia.interceptors.request.use((config) => {
    const token = opciones.obtenerToken()
    if (token) config.headers.set('Authorization', `Bearer ${token}`)
    return config
  })
  instancia.interceptors.response.use(
    (respuesta) => respuesta,
    (error: unknown) => {
      const normalizado = normalizarError(error)
      const token = opciones.obtenerToken()
      // Un 401 tardío de la sesión anterior no debe cerrar una sesión recién iniciada.
      const enviado = axios.isAxiosError(error) ? error.config?.headers?.get('Authorization') : null
      if (normalizado.status === 401 && token && enviado === `Bearer ${token}`)
        opciones.alNoAutenticado(normalizado)
      return Promise.reject(normalizado)
    },
  )
  return instancia
}

export const http = crearHttp({
  obtenerToken: () => useSesionStore().token,
  alNoAutenticado: (error) => useSesionStore().cerrar(error.code),
})
