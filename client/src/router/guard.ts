import { watch } from 'vue'
import type { Router, RouteLocationNormalized, RouteLocationRaw } from 'vue-router'
import type { Rol } from '@/types/api'
import type { ControlSesion } from '@/services/controlSesion'
export const INICIO_POR_ROL: Record<Rol, string> = {
  gerente: 'gerente-inicio',
  asistente: 'asistente-inicio',
}
export function resolverAcceso(
  destino: RouteLocationNormalized,
  rol: Rol | null,
): true | RouteLocationRaw {
  if (destino.meta.libre) return true
  if (destino.meta.publica) return rol ? { name: INICIO_POR_ROL[rol] } : true
  if (!rol) return { name: 'login', query: { redirect: destino.fullPath } }
  if (destino.meta.rol && destino.meta.rol !== rol) return { name: INICIO_POR_ROL[rol] }
  return true
}
export function retornoAutorizado(router: Router, ruta: unknown, rol: Rol): RouteLocationRaw {
  if (typeof ruta === 'string' && ruta.startsWith('/') && !ruta.startsWith('//')) {
    const destino = router.resolve(ruta)
    if (destino.matched.length && destino.meta.rol === rol) return destino.fullPath
  }
  return { name: INICIO_POR_ROL[rol] }
}
export function instalarAcceso(router: Router, control: ControlSesion) {
  const { sesion } = control
  const quitarGuard = router.beforeEach(async (destino) => {
    if (!destino.meta.libre && sesion.token) {
      try {
        await control.verificar()
      } catch {
        if (!destino.meta.publica)
          return { name: 'login', query: { motivo: 'sin-conexion', redirect: destino.fullPath } }
      }
    }
    // Una sesión local sin confirmar no abre pantallas ni redirige fuera del acceso.
    const rol = sesion.confirmada === sesion.token ? sesion.rol : null
    if (destino.meta.publica && rol) return retornoAutorizado(router, destino.query.redirect, rol)
    return resolverAcceso(destino, rol)
  })
  const quitarTitulo = router.afterEach((destino) => {
    document.title = destino.meta.titulo ? `${destino.meta.titulo} | Deconsta` : 'Deconsta'
  })
  const quitarSesion = watch(
    () => [sesion.token, sesion.rol],
    () => {
      const destino = router.currentRoute.value
      if (!destino.matched.length || destino.meta.libre || destino.meta.publica) return
      if (!sesion.token)
        void router.replace({
          name: 'login',
          query: { motivo: sesion.motivo || 'NO_AUTENTICADO', redirect: destino.fullPath },
        })
      else if (sesion.rol && destino.meta.rol !== sesion.rol)
        void router.replace({ name: INICIO_POR_ROL[sesion.rol] })
    },
    { flush: 'post' },
  )
  return () => {
    quitarGuard()
    quitarTitulo()
    quitarSesion()
  }
}
