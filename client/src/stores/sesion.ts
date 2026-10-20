import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { z } from 'zod'
import type { UsuarioSesion } from '@/types/api'

export const CLAVE_SESION = 'deconsta.sesion'
export const esquemaUsuario = z.object({
  id: z.string().min(1),
  rol: z.enum(['gerente', 'asistente']),
  nombre: z.string(),
})
const esquema = z.object({
  token: z.string().min(1),
  usuario: esquemaUsuario,
  actividad: z.number().finite().optional(),
})
type Sesion = z.infer<typeof esquema>
export function vencimiento(token: string): number {
  try {
    const parte = token.split('.')[1] || ''
    const datos = JSON.parse(atob(parte.replace(/-/g, '+').replace(/_/g, '/')))
    return typeof datos.exp === 'number' && Number.isFinite(datos.exp) ? datos.exp * 1000 : 0
  } catch {
    return 0
  }
}
function guardar(sesion: Sesion | null) {
  try {
    if (sesion) localStorage.setItem(CLAVE_SESION, JSON.stringify(sesion))
    else localStorage.removeItem(CLAVE_SESION)
  } catch {
    /* La sesión sigue en memoria si el navegador impide almacenar. */
  }
}
function leer(): Sesion | null {
  try {
    const texto = localStorage.getItem(CLAVE_SESION)
    return texto ? esquema.parse(JSON.parse(texto)) : null
  } catch {
    guardar(null)
    return null
  }
}
export const useSesionStore = defineStore('sesion', () => {
  const guardada = leer()
  const token = ref<string | null>(guardada?.token ?? null)
  const usuario = ref<UsuarioSesion | null>(guardada?.usuario ?? null)
  const ultimaActividad = ref(guardada?.actividad ?? Date.now())
  const confirmada = ref<string | null>(null)
  const motivo = ref('')
  const estaAutenticado = computed(() => token.value !== null && usuario.value !== null)
  const rol = computed(() => usuario.value?.rol ?? null)
  function aplicar(datos: Sesion) {
    if (
      token.value !== datos.token ||
      usuario.value?.id !== datos.usuario.id ||
      usuario.value?.rol !== datos.usuario.rol ||
      usuario.value?.nombre !== datos.usuario.nombre
    )
      confirmada.value = null
    token.value = datos.token
    usuario.value = datos.usuario
    ultimaActividad.value = datos.actividad ?? Date.now()
    motivo.value = ''
  }
  function iniciar(nuevoToken: string, nuevoUsuario: UsuarioSesion, actividad = Date.now()) {
    const datos = esquema.parse({ token: nuevoToken, usuario: nuevoUsuario, actividad })
    aplicar(datos)
    guardar(datos)
  }
  function cerrar(razon = 'manual', propagar = true) {
    motivo.value = razon
    token.value = null
    usuario.value = null
    confirmada.value = null
    if (propagar) guardar(null)
  }
  function sincronizar() {
    const datos = leer()
    if (datos) aplicar(datos)
    else cerrar('otra-pestana', false)
  }
  function registrarActividad() {
    // Adoptar primero una renovación que otra pestaña pudo guardar antes de su evento storage.
    try {
      if (!localStorage.getItem(CLAVE_SESION)) {
        cerrar('otra-pestana', false)
        return
      }
      const vigente = leer()
      if (!vigente) {
        cerrar('otra-pestana', false)
        return
      }
      if (vigente.usuario.id !== usuario.value?.id) {
        aplicar(vigente)
        return
      }
      aplicar(vigente)
    } catch {
      /* Sin almacenamiento, solo se actualiza la sesión en memoria. */
    }
    if (token.value && usuario.value) iniciar(token.value, usuario.value)
  }
  return {
    token,
    usuario,
    ultimaActividad,
    confirmada,
    motivo,
    estaAutenticado,
    rol,
    iniciar,
    cerrar,
    sincronizar,
    registrarActividad,
  }
})
