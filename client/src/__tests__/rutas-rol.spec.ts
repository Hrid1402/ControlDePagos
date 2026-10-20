import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView, type Router } from 'vue-router'
import PrimeVue from 'primevue/config'
import ConfirmationService from 'primevue/confirmationservice'
import { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import { rutas } from '@/router/rutas'
import { instalarAcceso } from '@/router/guard'
import { useSesionStore } from '@/stores/sesion'
import { crearHttp } from '@/api/http'
import { crearControlSesion, MINUTO, type ControlSesion } from '@/services/controlSesion'
import { configuracionUi } from '@/config/ui'
import type { Rol } from '@/types/api'

// H01 CA10 y CA11 sobre la tabla de rutas real, no sobre un router de prueba: una ruta nueva
// que olvide declarar su rol queda abierta para cualquier sesión y estas pruebas lo detectan.
const jwt = () => `e30.${btoa(JSON.stringify({ exp: (Date.now() + 30 * MINUTO) / 1000 }))}.firma`
let http: AxiosInstance
let control: ControlSesion
let rolServidor: Rol
const limpiezas: (() => void)[] = []
class Socket {
  close = vi.fn()
  send = vi.fn()
}
function errorApi(status: number, code: string, config: InternalAxiosRequestConfig) {
  const data = { code, detail: 'No tienes permiso para realizar esta acción.', field: null }
  return new AxiosError('HTTP', 'ERR_BAD_REQUEST', config, null, {
    status,
    data,
    statusText: '',
    headers: {},
    config,
  })
}
beforeEach(() => {
  vi.stubGlobal('WebSocket', Socket)
  localStorage.clear()
  setActivePinia(createPinia())
  const sesion = useSesionStore()
  http = crearHttp({
    obtenerToken: () => sesion.token,
    alNoAutenticado: (e) => sesion.cerrar(e.code),
  })
  // El servidor confirma la identidad en /auth/me y rechaza con 403 lo que no es del rol.
  http.defaults.adapter = async (config) => {
    if (config.url === '/auditoria' && rolServidor !== 'gerente')
      throw errorApi(403, 'SIN_PERMISO', config)
    return {
      data: { id: '1', nombre: 'Ana', rol: rolServidor },
      status: 200,
      statusText: '',
      headers: {},
      config,
    }
  }
  control = crearControlSesion(sesion, http)
})
afterEach(() => {
  limpiezas.splice(0).forEach((f) => f())
  control.detener()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
function routerReal(): Router {
  const router = createRouter({ history: createMemoryHistory(), routes: rutas })
  limpiezas.push(instalarAcceso(router, control))
  return router
}
function entrar(rol: Rol) {
  rolServidor = rol
  useSesionStore().iniciar(jwt(), { id: '1', nombre: 'Ana', rol })
}
/** Rutas de la tabla real que no son públicas ni libres, con el rol que heredan de su espacio. */
function protegidas(): { ruta: string; rol: Rol | undefined }[] {
  const router = createRouter({ history: createMemoryHistory(), routes: rutas })
  const vistas = new Map<string, Rol | undefined>()
  for (const registro of router.getRoutes()) {
    if (registro.redirect) continue
    const destino = router.resolve(registro.path)
    if (destino.meta.libre || destino.meta.publica) continue
    // La ampliación de RouteMeta (types/router.d.ts) no entra en el tsconfig de las pruebas.
    vistas.set(destino.fullPath, destino.meta.rol as Rol | undefined)
  }
  return [...vistas].map(([ruta, rol]) => ({ ruta, rol }))
}

describe('rutas por rol con la tabla real', () => {
  it('toda ruta protegida declara el rol de su espacio', () => {
    const rutasProtegidas = protegidas()
    expect(rutasProtegidas.map((r) => r.ruta)).toEqual(
      expect.arrayContaining(['/gerente', '/asistente']),
    )
    for (const { ruta, rol } of rutasProtegidas) {
      expect(rol, ruta).toBeDefined()
      expect(ruta.startsWith(`/${rol}`), ruta).toBe(true)
    }
  })

  it('sin sesión cada ruta protegida pide iniciar sesión y guarda a dónde iba (CA10)', async () => {
    const router = routerReal()
    for (const { ruta } of protegidas()) {
      await router.push(ruta)
      expect(router.currentRoute.value.name, ruta).toBe('login')
      expect(router.currentRoute.value.query.redirect, ruta).toBe(ruta)
    }
  })

  it.each(['gerente', 'asistente'] as const)(
    '%s: entra a sus rutas y ve sin permiso en las del otro rol (CA11)',
    async (rol) => {
      entrar(rol)
      const router = routerReal()
      const ajenas = protegidas().filter((r) => r.rol !== rol)
      expect(ajenas.length).toBeGreaterThan(0)
      for (const { ruta, rol: duena } of protegidas()) {
        await router.push(ruta)
        if (duena === rol) expect(router.currentRoute.value.fullPath, ruta).toBe(ruta)
        else expect(router.currentRoute.value.name, ruta).toBe('sin-permiso')
      }
    },
  )
})

describe('ocultar una opción del menú no autoriza', () => {
  it('el menú de la asistente no ofrece rutas del gerente y la API responde 403 sin cerrar la sesión', async () => {
    entrar('asistente')
    const router = routerReal()
    await router.push('/asistente')
    await router.isReady()
    const wrapper = mount(defineComponent({ setup: () => () => h(RouterView) }), {
      attachTo: document.body,
      global: { plugins: [router, [PrimeVue, configuracionUi], ConfirmationService] },
    })
    limpiezas.push(() => wrapper.unmount())
    await flushPromises()
    const enlaces = wrapper.findAll('a[href]').map((a) => a.attributes('href'))
    expect(enlaces).toContain('/asistente')
    expect(enlaces.filter((href) => href?.startsWith('/gerente'))).toEqual([])

    // Aunque llame directo a una función del gerente, la API la rechaza; un 403 no es una sesión
    // vencida, así que la sesión y la pantalla siguen donde estaban.
    const token = useSesionStore().token
    await expect(http.get('/auditoria')).rejects.toMatchObject({
      status: 403,
      code: 'SIN_PERMISO',
    })
    await flushPromises()
    expect(useSesionStore().token).toBe(token)
    expect(router.currentRoute.value.name).toBe('asistente-inicio')
  })
})
