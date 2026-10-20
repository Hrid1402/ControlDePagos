import { computed, ref, watch, type InjectionKey } from 'vue'
import type { AxiosInstance } from 'axios'
import { CLAVE_SESION, esquemaUsuario, useSesionStore, vencimiento } from '@/stores/sesion'
import { crearCanal } from './tiempoReal'

export const MINUTO = 60000
export function crearControlSesion(sesion: ReturnType<typeof useSesionStore>, http: AxiosInstance) {
  const ahora = ref(Date.now())
  const error = ref('')
  const renovando = ref(false)
  const advertencia = computed(
    () => !!sesion.token && ahora.value - sesion.ultimaActividad >= 28 * MINUTO,
  )
  const segundos = computed(() =>
    Math.max(0, Math.ceil((sesion.ultimaActividad + 30 * MINUTO - ahora.value) / 1000)),
  )
  let comprobacion: { token: string; promesa: Promise<boolean> } | undefined
  let iniciado = false
  let tokenCanal: string | null = null
  const formularios = new Set<() => boolean>()
  let ultimaRevision = 0
  let ultimoIntento = 0
  let pararToken: (() => void) | undefined
  let temporizador: ReturnType<typeof setInterval> | undefined
  const canal = crearCanal({
    obtenerToken: () => sesion.token,
    alInvalidar: (motivo) => sesion.cerrar(motivo),
    alResincronizar: () => {
      void verificar(true).catch(() => {})
    },
  })
  async function verificar(forzar = false): Promise<boolean> {
    const token = sesion.token
    if (!token) return false
    if (Date.now() - sesion.ultimaActividad >= 30 * MINUTO) {
      sesion.cerrar('inactividad')
      return false
    }
    if (vencimiento(token) <= Date.now()) {
      sesion.cerrar('NO_AUTENTICADO')
      return false
    }
    if (!forzar && sesion.confirmada === token) return true
    if (comprobacion?.token === token) return comprobacion.promesa
    const promesa = (async () => {
      try {
        const { data } = await http.get('/auth/me')
        if (sesion.token !== token) return false
        const usuario = esquemaUsuario.parse(data)
        // Revalidar identidad no debe sobrescribir la actividad compartida entre pestañas.
        sesion.usuario = usuario
        sesion.confirmada = token
        ultimaRevision = Date.now()
        error.value = ''
        if (iniciado && tokenCanal !== token) {
          tokenCanal = token
          canal.conectar(token)
        }
        return true
      } catch (fallo) {
        if (sesion.token !== token) return false
        error.value = 'No pudimos comprobar tu sesión. Revisa la conexión e intenta de nuevo.'
        throw fallo
      } finally {
        if (comprobacion?.token === token) comprobacion = undefined
      }
    })()
    comprobacion = { token, promesa }
    return promesa
  }
  async function renovar(continuar = false) {
    const token = sesion.token
    if (!token || renovando.value) return
    if (Date.now() - sesion.ultimaActividad >= 30 * MINUTO) {
      sesion.cerrar('inactividad')
      return
    }
    renovando.value = true
    ultimoIntento = Date.now()
    try {
      const { data } = await http.post('/auth/renovar')
      if (sesion.token !== token) return
      const usuario = esquemaUsuario.parse(data.usuario)
      if (typeof data.access_token !== 'string' || vencimiento(data.access_token) <= Date.now())
        throw new Error('Token inválido')
      // Una renovación tardía no debe resucitar una sesión ya cerrada o inactiva.
      if (Date.now() - sesion.ultimaActividad >= 30 * MINUTO) {
        sesion.cerrar('inactividad')
        return
      }
      sesion.iniciar(data.access_token, usuario, continuar ? Date.now() : sesion.ultimaActividad)
      sesion.confirmada = data.access_token
      ahora.value = Date.now()
      error.value = ''
    } catch {
      if (sesion.token === token)
        error.value =
          'No pudimos renovar la sesión. Revisa la conexión y vuelve a intentar antes de que termine el plazo.'
    } finally {
      renovando.value = false
    }
  }
  function comprobar() {
    ahora.value = Date.now()
    if (!sesion.token) return
    if (ahora.value - sesion.ultimaActividad >= 30 * MINUTO) {
      sesion.cerrar('inactividad')
      return
    }
    const restante = vencimiento(sesion.token) - ahora.value
    if (restante <= 0) {
      sesion.cerrar('NO_AUTENTICADO')
      return
    }
    if (!advertencia.value && restante <= 2 * MINUTO && ahora.value - ultimoIntento >= 15000)
      void renovar()
    if (ahora.value - ultimaRevision >= MINUTO) {
      ultimaRevision = ahora.value
      void verificar(true).catch(() => {})
    }
  }
  function actividad() {
    comprobar()
    if (sesion.token && !advertencia.value && Date.now() - sesion.ultimaActividad >= 1000)
      sesion.registrarActividad()
  }
  function almacenamiento(evento: StorageEvent) {
    try {
      if (evento.storageArea && evento.storageArea !== localStorage) return
    } catch {
      return
    }
    if (evento.key === CLAVE_SESION || evento.key === null) {
      sesion.sincronizar()
      comprobar()
    }
  }
  function despertar() {
    comprobar()
    if (sesion.token) void verificar(true).catch(() => {})
  }
  const entradas = ['pointerdown', 'keydown', 'scroll', 'touchstart']
  function detener() {
    iniciado = false
    tokenCanal = null
    clearInterval(temporizador)
    pararToken?.()
    canal.detener()
    entradas.forEach((nombre) => window.removeEventListener(nombre, actividad, true))
    window.removeEventListener('storage', almacenamiento)
    window.removeEventListener('online', despertar)
    document.removeEventListener('visibilitychange', despertar)
  }
  function iniciar() {
    detener()
    iniciado = true
    entradas.forEach((nombre) =>
      window.addEventListener(nombre, actividad, { capture: true, passive: true }),
    )
    window.addEventListener('storage', almacenamiento)
    window.addEventListener('online', despertar)
    document.addEventListener('visibilitychange', despertar)
    pararToken = watch(
      () => [sesion.token, sesion.usuario?.id, sesion.rol],
      async ([token]) => {
        if (!token) {
          canal.detener()
          tokenCanal = null
          error.value = ''
          return
        }
        try {
          await verificar()
        } catch {
          /* La interfaz ofrece reintentar. */
        }
      },
      { immediate: true, flush: 'sync' },
    )
    temporizador = setInterval(comprobar, 1000)
    comprobar()
  }
  return {
    sesion,
    formularios,
    hayCambios: () => [...formularios].some((hayCambios) => hayCambios()),
    advertencia,
    segundos,
    error,
    renovando,
    verificar,
    renovar,
    comprobar,
    iniciar,
    detener,
    canal,
  }
}
export type ControlSesion = ReturnType<typeof crearControlSesion>
export const controlSesionKey: InjectionKey<ControlSesion> = Symbol('controlSesion')
