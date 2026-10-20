import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, type RouteLocationNormalized } from 'vue-router'
import { nextTick } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { AxiosError, type AxiosInstance, type AxiosResponse } from 'axios'
import { CLAVE_SESION, useSesionStore, vencimiento } from '@/stores/sesion'
import { crearHttp } from '@/api/http'
import { crearControlSesion, MINUTO, type ControlSesion } from '@/services/controlSesion'
import { instalarAcceso, resolverAcceso, retornoAutorizado } from '@/router/guard'

const usuario = { id: '1', rol: 'gerente' as const, nombre: 'Ana' }
const inicio = new Date('2026-10-20T12:00:00Z').getTime()
const jwt = (exp = Date.now() + 30 * MINUTO) =>
  `e30.${btoa(JSON.stringify({ exp: exp / 1000 }))}.firma`
let control: ControlSesion
let http: AxiosInstance
let parar: (() => void) | undefined
class Socket {
  close = vi.fn()
  send = vi.fn()
}
beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(inicio)
  vi.stubGlobal('WebSocket', Socket)
  localStorage.clear()
  setActivePinia(createPinia())
  const sesion = useSesionStore()
  http = crearHttp({
    obtenerToken: () => sesion.token,
    alNoAutenticado: (e) => sesion.cerrar(e.code),
  })
  http.defaults.adapter = vi.fn(async (config) => ({
    data: config.url === '/auth/renovar' ? { access_token: jwt(), usuario } : usuario,
    status: 200,
    statusText: '',
    headers: {},
    config,
  }))
  control = crearControlSesion(sesion, http)
})
afterEach(() => {
  control.detener()
  parar?.()
  parar = undefined
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
const sesion = () => useSesionStore()
function entrar() {
  sesion().iniciar(jwt(), usuario)
}
function routerPrueba() {
  const pagina = { template: '<p>Página</p>' }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/login',
        name: 'login',
        component: pagina,
        meta: { publica: true, titulo: 'Acceso' },
      },
      {
        path: '/gerente/:resto(.*)*',
        name: 'gerente-inicio',
        component: pagina,
        meta: { rol: 'gerente', titulo: 'Mi espacio' },
      },
      {
        path: '/asistente',
        name: 'asistente-inicio',
        component: pagina,
        meta: { rol: 'asistente' },
      },
      { path: '/:resto(.*)*', name: 'no-encontrada', component: pagina, meta: { libre: true } },
    ],
  })
  parar = instalarAcceso(router, control)
  return router
}
describe('identidad confirmada y acceso', () => {
  it('no confía en el rol guardado: obtiene la identidad real antes de entrar', async () => {
    sesion().iniciar(jwt(), { ...usuario, rol: 'asistente' })
    const router = routerPrueba()
    await router.push('/gerente/deudas?estado=pendiente')
    expect(sesion().rol).toBe('gerente')
    expect(router.currentRoute.value.fullPath).toBe('/gerente/deudas?estado=pendiente')
    expect(document.title).toBe('Mi espacio | Deconsta')
  })
  it.each(['gerente', 'asistente'] as const)('protege las rutas de %s sin sesión', async (rol) => {
    const router = routerPrueba()
    await router.push(`/${rol}`)
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe(`/${rol}`)
  })
  it('redirige una ruta ajena y permite la propia', () => {
    const destino = {
      meta: { rol: 'gerente' },
      fullPath: '/gerente',
    } as unknown as RouteLocationNormalized
    expect(resolverAcceso(destino, 'asistente')).toEqual({ name: 'asistente-inicio' })
    expect(resolverAcceso(destino, 'gerente')).toBe(true)
  })
  it('retorna a una ruta propia conservando búsqueda y descarta destinos externos, públicos o ajenos', async () => {
    entrar()
    const router = routerPrueba()
    await router.push('/login?redirect=%2Fgerente%2Fdeudas%3Fpage%3D2')
    expect(router.currentRoute.value.fullPath).toBe('/gerente/deudas?page=2')
    for (const destino of [
      'https://ejemplo.com',
      '//ejemplo.com',
      '/asistente',
      '/login',
      '/inexistente',
      ['otra'],
    ])
      expect(retornoAutorizado(router, destino, 'gerente')).toEqual({ name: 'gerente-inicio' })
  })
  it('muestra no encontrada y usa Deconsta como título sin metadata', async () => {
    const router = routerPrueba()
    await router.push('/no-existe')
    expect(router.currentRoute.value.name).toBe('no-encontrada')
    expect(document.title).toBe('Deconsta')
  })
  it('un 401 revocado lleva al login con motivo y retorno', async () => {
    entrar()
    const router = routerPrueba()
    await router.push('/gerente')
    http.defaults.adapter = async (config) => {
      throw new AxiosError('revocada', 'ERR_BAD_RESPONSE', config, null, {
        status: 401,
        data: { code: 'SESION_REVOCADA' },
        config,
        headers: {},
        statusText: '',
      })
    }
    await control.verificar(true)
    await nextTick()
    await flushPromises()
    expect(sesion().token).toBeNull()
    expect(router.currentRoute.value.query).toMatchObject({
      motivo: 'SESION_REVOCADA',
      redirect: '/gerente',
    })
  })
  it('sin red no abre una ruta protegida ni borra una sesión aún vigente y permite reintentar', async () => {
    entrar()
    const adaptador = http.defaults.adapter
    http.defaults.adapter = async () => {
      throw new AxiosError('sin red', 'ERR_NETWORK')
    }
    const router = routerPrueba()
    await router.push('/gerente')
    expect(router.currentRoute.value.query.motivo).toBe('sin-conexion')
    expect(sesion().token).toBeTruthy()
    http.defaults.adapter = adaptador
    await router.replace('/gerente')
    expect(router.currentRoute.value.name).toBe('gerente-inicio')
  })
  it('rechaza tokens dañados y vencidos sin abrir el espacio', async () => {
    for (const token of ['roto', 'a.e30.b', jwt(inicio - 1)]) {
      sesion().iniciar(token, usuario)
      expect(await control.verificar()).toBe(false)
      expect(sesion().token).toBeNull()
    }
    expect(vencimiento('a.%%%.*')).toBe(0)
  })
  it('una verificación tardía no recupera una sesión cerrada', async () => {
    entrar()
    let completar!: (v: unknown) => void
    http.defaults.adapter = (config) =>
      new Promise<AxiosResponse>((resolve) => {
        completar = (data) => resolve({ data, config, status: 200, statusText: '', headers: {} })
      })
    const p = control.verificar()
    await flushPromises()
    sesion().cerrar()
    completar(usuario)
    expect(await p).toBe(false)
    expect(sesion().token).toBeNull()
  })
})
describe('inactividad y renovación', () => {
  it('avisa a los 28 y cierra a los 30 minutos, incluso tras suspender la pestaña', async () => {
    entrar()
    control.iniciar()
    await flushPromises()
    vi.setSystemTime(inicio + 28 * MINUTO)
    control.comprobar()
    expect(control.advertencia.value).toBe(true)
    expect(control.segundos.value).toBe(120)
    vi.setSystemTime(inicio + 31 * MINUTO)
    document.dispatchEvent(new Event('visibilitychange'))
    expect(sesion().motivo).toBe('inactividad')
    expect(sesion().token).toBeNull()
  })
  it('continuar renueva y reinicia la actividad solo al confirmar el servidor', async () => {
    entrar()
    vi.setSystemTime(inicio + 28 * MINUTO)
    control.comprobar()
    expect(control.advertencia.value).toBe(true)
    await control.renovar(true)
    expect(control.advertencia.value).toBe(false)
    expect(sesion().ultimaActividad).toBe(Date.now())
    expect(vencimiento(sesion().token!)).toBe(Date.now() + 30 * MINUTO)
  })
  it('renueva automáticamente con actividad reciente, sin reiniciar el reloj de inactividad', async () => {
    entrar()
    vi.setSystemTime(inicio + 27 * MINUTO)
    sesion().registrarActividad()
    vi.setSystemTime(inicio + 28 * MINUTO)
    control.comprobar()
    await flushPromises()
    expect(sesion().ultimaActividad).toBe(inicio + 27 * MINUTO)
    expect(vencimiento(sesion().token!)).toBe(inicio + 58 * MINUTO)
  })
  it('no oculta el aviso ni guarda una fecha nueva si continuar falla por red', async () => {
    entrar()
    vi.setSystemTime(inicio + 28 * MINUTO)
    control.comprobar()
    http.defaults.adapter = async () => {
      throw new AxiosError('sin red', 'ERR_NETWORK')
    }
    await control.renovar(true)
    expect(control.advertencia.value).toBe(true)
    expect(control.error.value).toContain('No pudimos renovar')
    expect(sesion().ultimaActividad).toBe(inicio)
  })
  it('no resucita una sesión por renovación tardía, y evita envíos simultáneos', async () => {
    entrar()
    let completar!: () => void
    http.defaults.adapter = vi.fn(
      (config) =>
        new Promise<AxiosResponse>((resolve) => {
          completar = () =>
            resolve({
              data: { access_token: jwt(), usuario },
              config,
              status: 200,
              statusText: '',
              headers: {},
            })
        }),
    )
    const p = control.renovar(true)
    await flushPromises()
    await control.renovar(true)
    expect(http.defaults.adapter).toHaveBeenCalledTimes(1)
    sesion().cerrar()
    completar()
    await p
    expect(sesion().token).toBeNull()
  })
  it('la interacción no revive un plazo agotado y la actividad normal sí se comparte', async () => {
    entrar()
    control.iniciar()
    await flushPromises()
    vi.setSystemTime(inicio + MINUTO)
    window.dispatchEvent(new Event('keydown'))
    expect(sesion().ultimaActividad).toBe(Date.now())
    vi.setSystemTime(inicio + 32 * MINUTO)
    window.dispatchEvent(new Event('pointerdown'))
    expect(sesion().token).toBeNull()
  })
  it('el aviso exige continuar explícitamente y no se cancela moviendo la página', async () => {
    entrar()
    control.iniciar()
    await flushPromises()
    vi.setSystemTime(inicio + 28 * MINUTO)
    window.dispatchEvent(new Event('scroll'))
    expect(control.advertencia.value).toBe(true)
    expect(sesion().ultimaActividad).toBe(inicio)
  })
})
describe('coordinación de pestañas', () => {
  it('revalidar identidad no sobrescribe actividad de otra pestaña', async () => {
    entrar()
    let completar!: () => void
    http.defaults.adapter = (config) =>
      new Promise<AxiosResponse>((resolve) => {
        completar = () =>
          resolve({ data: usuario, config, status: 200, statusText: '', headers: {} })
      })
    const p = control.verificar()
    await flushPromises()
    const guardada = JSON.parse(localStorage.getItem(CLAVE_SESION)!)
    guardada.actividad = inicio + MINUTO
    localStorage.setItem(CLAVE_SESION, JSON.stringify(guardada))
    completar()
    await p
    expect(JSON.parse(localStorage.getItem(CLAVE_SESION)!).actividad).toBe(inicio + MINUTO)
  })
  it('invalidar una identidad local modificada exige confirmarla de nuevo', async () => {
    entrar()
    await control.verificar()
    const datos = JSON.parse(localStorage.getItem(CLAVE_SESION)!)
    datos.usuario.rol = 'asistente'
    localStorage.setItem(CLAVE_SESION, JSON.stringify(datos))
    sesion().sincronizar()
    expect(sesion().confirmada).toBeNull()
    await control.verificar()
    expect(sesion().rol).toBe('gerente')
  })

  it('adopta token y actividad de otra pestaña y propaga su cierre', async () => {
    entrar()
    control.iniciar()
    await flushPromises()
    const token = jwt(inicio + 45 * MINUTO)
    localStorage.setItem(
      CLAVE_SESION,
      JSON.stringify({ token, usuario, actividad: inicio + MINUTO }),
    )
    window.dispatchEvent(new StorageEvent('storage', { key: CLAVE_SESION }))
    expect(sesion().token).toBe(token)
    expect(sesion().ultimaActividad).toBe(inicio + MINUTO)
    localStorage.removeItem(CLAVE_SESION)
    window.dispatchEvent(new StorageEvent('storage', { key: CLAVE_SESION }))
    expect(sesion().token).toBeNull()
    expect(sesion().motivo).toBe('otra-pestana')
  })
  it('no sobrescribe un cierre remoto pendiente al registrar actividad', () => {
    entrar()
    localStorage.removeItem(CLAVE_SESION)
    sesion().registrarActividad()
    expect(sesion().token).toBeNull()
    expect(localStorage.getItem(CLAVE_SESION)).toBeNull()
  })
  it('conserva el plazo de inactividad al recargar', async () => {
    entrar()
    vi.setSystemTime(inicio + 29 * MINUTO)
    setActivePinia(createPinia())
    const nueva = crearControlSesion(sesion(), http)
    nueva.comprobar()
    expect(nueva.advertencia.value).toBe(true)
    vi.setSystemTime(inicio + 30 * MINUTO)
    nueva.comprobar()
    expect(sesion().token).toBeNull()
    nueva.detener()
  })
})
