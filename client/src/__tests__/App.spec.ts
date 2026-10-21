import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type RouteLocationNormalized } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import App from '../App.vue'
import { http } from '@/api/http'
import { rutas } from '@/router/rutas'
import { resolverAcceso } from '@/router/guard'
import { CLAVE_SESION, useSesionStore } from '@/stores/sesion'
import { configuracionUi } from '../config/ui'

const CLAVE = 'Clave-secreta-9!'
const NUEVA = 'Nueva-clave-segura-7!'
const TOKEN_ENLACE = 'token-del-enlace-123'
const GENERICO =
  'Si el usuario existe y tiene un correo registrado, te enviamos un enlace para restablecer la contraseña.'
const jwt = () => `e30.${btoa(JSON.stringify({ exp: (Date.now() + 30 * 60000) / 1000 }))}.firma`

interface Peticion {
  url?: string
  cuerpo?: Record<string, unknown>
}
type Salida = { status: number; data: unknown } | 'sin-red'
type Respuesta = Salida | Promise<Salida>
let wrapper: VueWrapper | undefined
let peticiones: Peticion[] = []

function responder(fn: (url: string) => Respuesta) {
  peticiones = []
  http.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    peticiones.push({ url: config.url, cuerpo: config.data ? JSON.parse(config.data) : undefined })
    const salida = await fn(config.url ?? '')
    if (salida === 'sin-red') throw new AxiosError('sin red', 'ERR_NETWORK')
    const respuesta = { ...salida, config, headers: {}, statusText: '' }
    if (salida.status >= 400)
      throw new AxiosError('error', 'ERR_BAD_RESPONSE', config, null, respuesta)
    return respuesta
  }
}
const errorApi = (status: number, code: string, detail: string, field: string | null = null) =>
  ({ status, data: { code, detail, field } }) as const

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  setActivePinia(createPinia())
  responder(() => errorApi(500, 'ERROR_INTERNO', 'Sin configurar.'))
})
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function abrir(ruta = '/') {
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  const router = createRouter({ history: createMemoryHistory(), routes: rutas })
  await router.push(ruta)
  await router.isReady()
  wrapper = mount(App, {
    attachTo: document.body,
    global: {
      plugins: [router, [PrimeVue, configuracionUi], ToastService, ConfirmationService],
    },
  })
  return { router, pagina: wrapper }
}
async function escribir(pagina: VueWrapper, valores: Record<string, string>) {
  for (const [nombre, valor] of Object.entries(valores))
    await pagina.get(`input[name="${nombre}"]`).setValue(valor)
}
async function enviar(pagina: VueWrapper) {
  await pagina.get('form').trigger('submit')
  // La validación del formulario es asíncrona: se espera a que termine antes de comprobar.
  await flushPromises()
  await new Promise((resolver) => setTimeout(resolver, 5))
  await flushPromises()
}
const valor = (pagina: VueWrapper, nombre: string) =>
  (pagina.get(`input[name="${nombre}"]`).element as HTMLInputElement).value
const almacenado = () => JSON.stringify([{ ...localStorage }, { ...sessionStorage }])

describe('acceso de Deconsta', () => {
  it('presenta el login como raíz, con marca y sin controles de revisión', async () => {
    const { pagina, router } = await abrir()
    expect(router.currentRoute.value.name).toBe('login')
    expect(pagina.get('h1').text()).toBe('Todo en su lugar.')
    expect(pagina.get('img[alt="Deconsta"]').attributes('src')).toContain(
      'deconsta-wordmark-white.svg',
    )
    expect(pagina.find('input[name="username"]').exists()).toBe(true)
    expect(pagina.find('.selector-revision').exists()).toBe(false)
  })
  it('conserva motivo y retorno al redirigir enlaces antiguos al login', async () => {
    const { router, pagina } = await abrir('/login?motivo=inactividad&redirect=/gerente#entrada')
    expect(router.currentRoute.value.path).toBe('/')
    expect(router.currentRoute.value.query.redirect).toBe('/gerente')
    expect(router.currentRoute.value.hash).toBe('#entrada')
    expect(pagina.text()).toContain('30 minutos sin actividad')
  })
  it('ofrece retorno al acceso desde una página sin permiso', async () => {
    const { pagina, router } = await abrir('/sin-permiso')
    expect(pagina.get('h1').text()).toBe('Este espacio no es el tuyo.')
    await pagina.get('.boton-acceso').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/')
  })
  it('en la revisión visual los formularios no llaman a la API', async () => {
    const { pagina } = await abrir('/?revision=1')
    expect(pagina.find('.selector-revision').exists()).toBe(true)
    await escribir(pagina, { username: 'revision', contrasena: CLAVE })
    await enviar(pagina)
    expect(peticiones).toEqual([])
    expect(pagina.text()).toContain('Revisión visual: no se envió nada.')
  })
})

describe('ingreso conectado a la API', () => {
  it.each([
    ['gerente', '/gerente'],
    ['asistente', '/asistente'],
  ] as const)('el %s entra a su espacio y la sesión no guarda la contraseña', async (rol, ruta) => {
    const token = jwt()
    responder(() => ({
      status: 200,
      data: { access_token: token, token_type: 'bearer', usuario: { id: '1', nombre: 'Ana', rol } },
    }))
    const { pagina, router } = await abrir()
    await escribir(pagina, { username: '  Ana.Paz ', contrasena: CLAVE })
    await enviar(pagina)
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe(ruta))
    expect(peticiones[0]).toEqual({
      url: '/auth/login',
      cuerpo: { username: 'Ana.Paz', contrasena: CLAVE },
    })
    // Después solo se lee el perfil, para saber si falta aceptar la política (H02 CA10), y lo que
    // muestra el inicio: la asistente entra a su bandeja (H15 CA01).
    expect(
      peticiones
        .slice(1)
        .map((p) => p.url)
        .sort(),
    ).toEqual(
      rol === 'gerente' ? ['/usuarios/perfil'] : ['/bandeja', '/categorias', '/usuarios/perfil'],
    )
    expect(useSesionStore().token).toBe(token)
    expect(JSON.parse(localStorage.getItem(CLAVE_SESION) ?? '{}').token).toBe(token)
    expect(almacenado()).not.toContain(CLAVE)
    expect(JSON.stringify(useSesionStore().$state)).not.toContain(CLAVE)
  })
  it.each([
    ['/gerente?vista=pagos', 'gerente', '/gerente?vista=pagos'],
    ['/asistente', 'gerente', '/gerente'],
    ['//ejemplo.com', 'asistente', '/asistente'],
    ['/gerente', 'asistente', '/asistente'],
  ] as const)(
    'con retorno %s el %s va a %s (solo si es de su rol)',
    async (redirect, rol, final) => {
      responder(() => ({
        status: 200,
        data: { access_token: jwt(), usuario: { id: '1', nombre: 'Ana', rol } },
      }))
      const { pagina, router } = await abrir(`/?redirect=${encodeURIComponent(redirect)}`)
      await escribir(pagina, { username: 'ana', contrasena: CLAVE })
      await enviar(pagina)
      await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe(final))
    },
  )
  it('deja el botón desactivado y envía una sola vez mientras procesa', async () => {
    let terminar: (r: Salida) => void = () => {}
    responder(() => new Promise<Salida>((resolver) => (terminar = resolver)))
    const { pagina } = await abrir()
    await escribir(pagina, { username: 'ana', contrasena: CLAVE })
    await enviar(pagina)
    expect(pagina.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(pagina.get('button[type="submit"]').text()).toContain('Entrando')
    await pagina.get('form').trigger('submit')
    await flushPromises()
    expect(peticiones).toHaveLength(1)
    terminar(errorApi(401, 'CREDENCIALES_INVALIDAS', 'Usuario o contraseña incorrectos.'))
    await flushPromises()
    expect(pagina.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })
  it('credenciales incorrectas: mensaje genérico, conserva el usuario y pide la contraseña', async () => {
    responder(() => errorApi(401, 'CREDENCIALES_INVALIDAS', 'Usuario o contraseña incorrectos.'))
    const { pagina, router } = await abrir()
    await escribir(pagina, { username: 'ana', contrasena: CLAVE })
    await enviar(pagina)
    await vi.waitFor(() =>
      expect(pagina.get('[role="alert"]').text()).toContain('Usuario o contraseña incorrectos.'),
    )
    expect(valor(pagina, 'username')).toBe('ana')
    expect(valor(pagina, 'contrasena')).toBe('')
    expect(document.activeElement).toBe(pagina.get('input[name="contrasena"]').element)
    expect(useSesionStore().token).toBeNull()
    expect(router.currentRoute.value.path).toBe('/')
  })
  it.each([
    [
      'cuenta bloqueada con los minutos del servidor',
      errorApi(
        423,
        'CUENTA_BLOQUEADA',
        'Tu cuenta está bloqueada por intentos fallidos. Intenta de nuevo en 15 minutos.',
      ),
      'Intenta de nuevo en 15 minutos.',
    ],
    [
      'cuenta inactiva con el texto de CA07',
      errorApi(403, 'CUENTA_INACTIVA', 'Cuenta inactiva, contacta al gerente.'),
      'Cuenta inactiva, contacta al gerente.',
    ],
    [
      'servidor caído',
      errorApi(500, 'ERROR_INTERNO', 'Ocurrió un error inesperado. Intenta de nuevo.'),
      'Ocurrió un error inesperado.',
    ],
    ['sin conexión', 'sin-red' as const, 'No hay conexión con el servidor.'],
  ])('%s se muestra y conserva lo escrito', async (_, respuesta, texto) => {
    responder(() => respuesta)
    const { pagina } = await abrir()
    await escribir(pagina, { username: 'ana', contrasena: CLAVE })
    await enviar(pagina)
    await vi.waitFor(() => expect(pagina.get('[role="alert"]').text()).toContain(texto))
    expect(valor(pagina, 'username')).toBe('ana')
    expect(valor(pagina, 'contrasena')).toBe(CLAVE)
    expect(pagina.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    expect(useSesionStore().token).toBeNull()
  })
  it('un 422 por campo se muestra en línea y enfoca ese campo', async () => {
    responder(() => errorApi(422, 'VALIDACION', 'Este campo es obligatorio.', 'contrasena'))
    const { pagina } = await abrir()
    await escribir(pagina, { username: 'ana', contrasena: CLAVE })
    await enviar(pagina)
    await vi.waitFor(() => expect(pagina.find('small.error').exists()).toBe(true))
    expect(pagina.get('small.error').text()).toBe('Este campo es obligatorio.')
    expect(document.activeElement).toBe(pagina.get('input[name="contrasena"]').element)
  })
  it('con campos vacíos no llama a la API y enfoca el primero', async () => {
    const { pagina } = await abrir()
    await enviar(pagina)
    await vi.waitFor(() => expect(pagina.text()).toContain('Escribe tu usuario.'))
    expect(peticiones).toEqual([])
    expect(document.activeElement).toBe(pagina.get('input[name="username"]').element)
  })
})

describe('recuperación por usuario', () => {
  it('envía el usuario y muestra la respuesta genérica sin decir si existe', async () => {
    responder(() => ({ status: 200, data: { detail: GENERICO } }))
    const { pagina, router } = await abrir('/recuperar')
    await escribir(pagina, { username: ' Ana.Paz ' })
    await enviar(pagina)
    await vi.waitFor(() => expect(pagina.get('h1').text()).toBe('Revisa tu correo.'))
    expect(peticiones).toEqual([
      { url: '/auth/recuperar-contrasena', cuerpo: { username: 'Ana.Paz' } },
    ])
    expect(pagina.text()).toContain(GENERICO)
    expect(router.currentRoute.value.name).toBe('recuperar')
    await pagina
      .findAll('button')
      .find((b) => b.text().includes('Probar con otro usuario'))!
      .trigger('click')
    await flushPromises()
    expect(pagina.find('input[name="username"]').exists()).toBe(true)
    expect(valor(pagina, 'username')).toBe('')
  })
  it('sin conexión avisa y conserva el usuario escrito', async () => {
    responder(() => 'sin-red')
    const { pagina } = await abrir('/recuperar')
    await escribir(pagina, { username: 'ana' })
    await enviar(pagina)
    await vi.waitFor(() =>
      expect(pagina.get('[role="alert"]').text()).toContain('No hay conexión con el servidor.'),
    )
    expect(valor(pagina, 'username')).toBe('ana')
  })
  it('un 422 del servidor se muestra en el campo del usuario', async () => {
    responder(() => errorApi(422, 'VALIDACION', 'El valor no es válido.', 'username'))
    const { pagina } = await abrir('/recuperar')
    await escribir(pagina, { username: 'ana' })
    await enviar(pagina)
    await vi.waitFor(() => expect(pagina.get('small.error').text()).toBe('El valor no es válido.'))
    expect(document.activeElement).toBe(pagina.get('input[name="username"]').element)
  })
})

describe('restablecer la contraseña', () => {
  it('lee el token del enlace, lo quita de la dirección y lo envía solo en el cuerpo', async () => {
    responder(() => ({ status: 200, data: { detail: 'Contraseña restablecida exitosamente.' } }))
    const { pagina, router } = await abrir(`/restablecer/${TOKEN_ENLACE}`)
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/restablecer')
    await escribir(pagina, { nueva: NUEVA, confirmar: NUEVA })
    await enviar(pagina)
    await vi.waitFor(() => expect(pagina.get('h1').text()).toContain('otra clave'))
    expect(peticiones).toEqual([
      {
        url: '/auth/restablecer-contrasena',
        cuerpo: { token: TOKEN_ENLACE, nueva_contrasena: NUEVA },
      },
    ])
    expect(almacenado()).not.toContain(TOKEN_ENLACE)
    expect(almacenado()).not.toContain(NUEVA)
    await pagina.get('.boton-acceso').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/')
  })
  it('un token vencido o usado lleva a pedir otro enlace', async () => {
    responder(() =>
      errorApi(400, 'TOKEN_INVALIDO', 'El token de restablecimiento es inválido o expiró.'),
    )
    const { pagina, router } = await abrir(`/restablecer/${TOKEN_ENLACE}`)
    await flushPromises()
    await escribir(pagina, { nueva: NUEVA, confirmar: NUEVA })
    await enviar(pagina)
    await vi.waitFor(() => expect(pagina.get('h1').text()).toBe('Necesitas un nuevo enlace.'))
    await pagina.get('.boton-acceso').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('recuperar')
  })
  it('sin token en la dirección no muestra el formulario ni llama a la API', async () => {
    const { pagina } = await abrir('/restablecer')
    expect(pagina.get('h1').text()).toBe('Necesitas un nuevo enlace.')
    expect(pagina.find('input[name="nueva"]').exists()).toBe(false)
    expect(peticiones).toEqual([])
  })
  it('muestra en línea el rechazo de las últimas 3 contraseñas y conserva el formulario', async () => {
    const motivo = 'La nueva contraseña no puede ser igual a la actual ni a las últimas 3.'
    responder(() => errorApi(400, 'CONTRASENA_REPETIDA', motivo, 'nueva_contrasena'))
    const { pagina } = await abrir(`/restablecer/${TOKEN_ENLACE}`)
    await flushPromises()
    await escribir(pagina, { nueva: NUEVA, confirmar: NUEVA })
    await enviar(pagina)
    await vi.waitFor(() => expect(pagina.get('small.error').text()).toBe(motivo))
    expect(valor(pagina, 'nueva')).toBe(NUEVA)
    expect(document.activeElement).toBe(pagina.get('input[name="nueva"]').element)
  })
  it('muestra el motivo específico de contraseña débil que devuelve la API', async () => {
    responder(() =>
      errorApi(
        422,
        'VALIDACION',
        'La contraseña debe tener mayúscula, minúscula, número y símbolo.',
        'nueva_contrasena',
      ),
    )
    const { pagina } = await abrir(`/restablecer/${TOKEN_ENLACE}`)
    await flushPromises()
    await escribir(pagina, { nueva: NUEVA, confirmar: NUEVA })
    await enviar(pagina)
    await vi.waitFor(() => expect(pagina.get('small.error').text()).toContain('mayúscula'))
  })
  it('el enlace se abre aunque haya otra sesión iniciada', async () => {
    const { router } = await abrir()
    const destino = router.resolve(
      `/restablecer/${TOKEN_ENLACE}`,
    ) as unknown as RouteLocationNormalized
    expect(resolverAcceso(destino, 'gerente')).toBe(true)
    expect(resolverAcceso(destino, null)).toBe(true)
  })
})
