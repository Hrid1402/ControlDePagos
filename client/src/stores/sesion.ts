import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { z } from 'zod'
import type { UsuarioSesion } from '@/types/api'

export const CLAVE_SESION = 'deconsta.sesion'
const esquema = z.object({
  token: z.string().min(1),
  usuario: z.object({
    id: z.string().min(1),
    rol: z.enum(['gerente', 'asistente']),
    nombre: z.string(),
  }),
})
type Sesion = z.infer<typeof esquema>

function guardar(sesion: Sesion | null) {
  try {
    if (sesion) localStorage.setItem(CLAVE_SESION, JSON.stringify(sesion))
    else localStorage.removeItem(CLAVE_SESION)
  } catch {
    /* Si el navegador impide almacenar, la sesión vive solo en memoria. */
  }
}

function leer(): Sesion | null {
  try {
    const texto = localStorage.getItem(CLAVE_SESION)
    if (!texto) return null
    return esquema.parse(JSON.parse(texto))
  } catch {
    guardar(null)
    return null
  }
}

export const useSesionStore = defineStore('sesion', () => {
  const guardada = leer()
  const token = ref<string | null>(guardada?.token ?? null)
  const usuario = ref<UsuarioSesion | null>(guardada?.usuario ?? null)
  const estaAutenticado = computed(() => token.value !== null && usuario.value !== null)
  const rol = computed(() => usuario.value?.rol ?? null)

  function iniciar(nuevoToken: string, nuevoUsuario: UsuarioSesion) {
    const sesion = esquema.parse({ token: nuevoToken, usuario: nuevoUsuario })
    token.value = sesion.token
    usuario.value = sesion.usuario
    guardar(sesion)
  }

  function cerrar() {
    token.value = null
    usuario.value = null
    guardar(null)
  }

  return { token, usuario, estaAutenticado, rol, iniciar, cerrar }
})
