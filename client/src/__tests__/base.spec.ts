import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { AxiosError, AxiosHeaders, CanceledError, type InternalAxiosRequestConfig } from 'axios'
import { z } from 'zod'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import ConfirmDialog from 'primevue/confirmdialog'
import Toast from 'primevue/toast'
import { crearHttp, normalizarError } from '@/api/http'
import { CLAVE_SESION, useSesionStore } from '@/stores/sesion'
import { configuracionUi } from '@/config/ui'
import FormularioBase from '@/components/formularios/FormularioBase.vue'
import CampoTexto from '@/components/formularios/CampoTexto.vue'

const usuario = { id: 'gerente-1', rol: 'gerente' as const, nombre: 'Ana' }
const montados: VueWrapper[] = []
beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})
afterEach(() => {
  montados.splice(0).forEach((w) => w.unmount())
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
function errorHttp(status: number, data: unknown, config?: InternalAxiosRequestConfig) {
  const c = config || ({ headers: new AxiosHeaders() } as InternalAxiosRequestConfig)
  return new AxiosError('HTTP', 'ERR_BAD_RESPONSE', c, null, {
    status,
    data,
    statusText: '',
    headers: {},
    config: c,
  })
}

describe('sesión', () => {
  it('persiste token identidad y actividad; cerrar limpia todo', () => {
    const sesion = useSesionStore()
    expect(sesion.estaAutenticado).toBe(false)
    sesion.iniciar('token', usuario)
    setActivePinia(createPinia())
    expect(useSesionStore().rol).toBe('gerente')
    expect(useSesionStore().token).toBe('token')
    expect(JSON.parse(localStorage.getItem(CLAVE_SESION)!)).toEqual({
      token: 'token',
      usuario,
      actividad: expect.any(Number),
    })
    useSesionStore().cerrar()
    expect(useSesionStore().usuario).toBeNull()
    expect(localStorage.getItem(CLAVE_SESION)).toBeNull()
  })
  it.each(['{dañado', JSON.stringify({ token: 'x', usuario: { ...usuario, rol: 'admin' } })])(
    'descarta datos corruptos: %s',
    (datos) => {
      localStorage.setItem(CLAVE_SESION, datos)
      expect(useSesionStore().token).toBeNull()
      expect(localStorage.getItem(CLAVE_SESION)).toBeNull()
    },
  )
  it('tolera almacenamiento bloqueado', () => {
    for (const metodo of ['getItem', 'setItem', 'removeItem'] as const)
      vi.spyOn(Storage.prototype, metodo).mockImplementation(() => {
        throw new Error('bloqueado')
      })
    const sesion = useSesionStore()
    sesion.iniciar('token', usuario)
    expect(sesion.estaAutenticado).toBe(true)
    sesion.cerrar()
    expect(sesion.rol).toBeNull()
  })
})

describe('HTTP', () => {
  it('envía siempre el token vigente', async () => {
    let token: string | null = 'uno'
    const http = crearHttp({ obtenerToken: () => token, alNoAutenticado: vi.fn() })
    http.defaults.adapter = async (config) => ({
      data: config.headers.Authorization,
      status: 200,
      statusText: '',
      headers: {},
      config,
    })
    expect((await http.get('/me')).data).toBe('Bearer uno')
    token = 'dos'
    expect((await http.get('/me')).data).toBe('Bearer dos')
    token = null
    expect((await http.get('/me')).data).toBeUndefined()
  })
  it('normaliza campos y respuestas mal formadas', () => {
    expect(
      normalizarError(
        errorHttp(422, { code: 'VALIDACION', detail: 'Revisa correo', field: 'correo' }),
      ),
    ).toEqual({ status: 422, code: 'VALIDACION', detail: 'Revisa correo', field: 'correo' })
    for (const cuerpo of ['<html>Fallo</html>', { detail: { interno: true }, field: 5 }])
      expect(normalizarError(errorHttp(502, cuerpo))).toMatchObject({
        status: 502,
        code: 'ERROR_HTTP',
        field: null,
      })
  })
  it.each([
    ['ERR_NETWORK', 'SIN_CONEXION'],
    ['ECONNABORTED', 'TIEMPO_AGOTADO'],
    ['ETIMEDOUT', 'TIEMPO_AGOTADO'],
  ])('distingue %s', (codigo, esperado) => {
    expect(normalizarError(new AxiosError('fallo', codigo)).code).toBe(esperado)
  })
  it('distingue cancelaciones y errores internos', () => {
    expect(normalizarError(new CanceledError()).code).toBe('CANCELADA')
    expect(normalizarError(new Error()).code).toBe('ERROR_INTERNO')
  })
  it.each([true, false])('cierra solo sesiones existentes ante 401: %s', async (existe) => {
    const cerrar = vi.fn()
    const http = crearHttp({
      obtenerToken: () => (existe ? 'token' : null),
      alNoAutenticado: cerrar,
    })
    http.defaults.adapter = async (config) => {
      throw errorHttp(401, {}, config)
    }
    await expect(http.get('/me')).rejects.toMatchObject({ status: 401 })
    expect(cerrar).toHaveBeenCalledTimes(existe ? 1 : 0)
  })
  it('un 401 tardío no cierra una sesión nueva', async () => {
    let token = 'anterior'
    const cerrar = vi.fn()
    const http = crearHttp({ obtenerToken: () => token, alNoAutenticado: cerrar })
    http.defaults.adapter = async (config) => {
      token = 'nueva'
      throw errorHttp(401, {}, config)
    }
    await expect(http.get('/me')).rejects.toMatchObject({ status: 401 })
    expect(cerrar).not.toHaveBeenCalled()
  })
})

async function formulario(
  guardar = vi.fn<(v: Record<string, unknown>) => Promise<unknown>>().mockResolvedValue({}),
  nombre = 'nombre',
) {
  const pagina = defineComponent({
    setup: () => () =>
      h(
        FormularioBase,
        {
          esquema: z.object({ [nombre]: z.string().min(3, 'Escribe al menos tres caracteres') }),
          valoresIniciales: { [nombre]: '' },
          guardar,
        },
        {
          default: () => h(CampoTexto, { nombre, etiqueta: nombre, ayuda: 'Dato del formulario' }),
        },
      ),
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: pagina },
      { path: '/otra', component: { template: '<p>Otra página</p>' } },
    ],
  })
  await router.push('/')
  await router.isReady()
  const raiz = defineComponent({
    setup: () => () => h('div', [h(RouterView), h(ConfirmDialog), h(Toast)]),
  })
  const wrapper = mount(raiz, {
    attachTo: document.body,
    global: { plugins: [router, [PrimeVue, configuracionUi], ConfirmationService, ToastService] },
  })
  montados.push(wrapper)
  await flushPromises()
  return { wrapper, router, guardar }
}
async function escribir(wrapper: VueWrapper, valor: string) {
  await wrapper.get('input').setValue(valor)
  await flushPromises()
}
async function enviar(wrapper: VueWrapper) {
  await wrapper.get('form').trigger('submit')
  await new Promise((resolve) => setTimeout(resolve, 30))
  await flushPromises()
}

describe('formularios reales y controles compartidos', () => {
  it.each(['nombre', 'alias'])('valida y guarda un formulario de %s', async (nombre) => {
    const { wrapper, guardar } = await formulario(undefined, nombre)
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('label').attributes('for')).toBe(wrapper.get('input').attributes('id'))
    await escribir(wrapper, 'a')
    await enviar(wrapper)
    expect(guardar).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Escribe al menos tres caracteres')
    expect(wrapper.get('input').attributes('aria-invalid')).toBe('true')
    await escribir(wrapper, 'Ana')
    await enviar(wrapper)
    await vi.waitFor(() => expect(guardar).toHaveBeenCalledWith({ [nombre]: 'Ana' }))
    expect(document.body.textContent).toContain('Los cambios se guardaron.')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  })
  it('impide doble envío y bloquea campos mientras guarda', async () => {
    let terminar!: () => void
    const guardar = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          terminar = resolve
        }),
    )
    const { wrapper } = await formulario(guardar)
    await escribir(wrapper, 'Ana')
    await enviar(wrapper)
    await vi.waitFor(() => expect(guardar).toHaveBeenCalledOnce())
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    await enviar(wrapper)
    expect(guardar).toHaveBeenCalledOnce()
    terminar()
    await flushPromises()
  })
  it('conserva valores y muestra errores del servidor en su campo', async () => {
    const guardar = vi
      .fn()
      .mockRejectedValueOnce({
        status: 409,
        code: 'DUPLICADO',
        detail: 'El nombre ya existe',
        field: 'nombre',
      })
      .mockResolvedValue({})
    const { wrapper } = await formulario(guardar)
    await escribir(wrapper, 'Ana')
    await enviar(wrapper)
    expect(wrapper.text()).toContain('El nombre ya existe')
    expect(wrapper.get('input').element.value).toBe('Ana')
    await escribir(wrapper, 'Ana María')
    await enviar(wrapper)
    expect(guardar).toHaveBeenCalledTimes(2)
  })
  it.each([{ code: 'SIN_CONEXION', detail: 'Sin conexión' }, new Error('interno')])(
    'conserva valores ante fallos generales',
    async (error) => {
      const { wrapper } = await formulario(vi.fn().mockRejectedValue(error))
      await escribir(wrapper, 'Ana')
      await enviar(wrapper)
      expect(wrapper.get('input').element.value).toBe('Ana')
      expect(wrapper.find('[data-pc-name="message"]').exists()).toBe(true)
      expect(localStorage.length).toBe(0)
      expect(sessionStorage.length).toBe(0)
    },
  )
  it('permite editar sin red y reintentar al reconectar', async () => {
    const { wrapper, guardar } = await formulario()
    window.dispatchEvent(new Event('offline'))
    await escribir(wrapper, 'Ana')
    expect(wrapper.text()).toContain('No tienes conexión')
    await enviar(wrapper)
    expect(guardar).not.toHaveBeenCalled()
    window.dispatchEvent(new Event('online'))
    await enviar(wrapper)
    expect(guardar).toHaveBeenCalledOnce()
  })
  it('avisa antes de cerrar o navegar, permite continuar o salir', async () => {
    const { wrapper, router } = await formulario()
    await escribir(wrapper, 'Ana')
    const evento = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(evento)
    expect(evento.defaultPrevented).toBe(true)
    const intento = router.push('/otra')
    await flushPromises()
    await vi.waitFor(() => expect(document.body.textContent).toContain('Seguir editando'))
    const cancelar = [...document.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('Seguir editando'),
    )
    expect(cancelar).toBeDefined()
    cancelar!.click()
    await intento
    expect(router.currentRoute.value.path).toBe('/')
    expect(wrapper.get('input').element.value).toBe('Ana')
    const salir = router.push('/otra')
    await flushPromises()
    ;[...document.querySelectorAll('button')]
      .find((b) => b.textContent?.includes('Salir sin guardar'))!
      .click()
    await salir
    expect(router.currentRoute.value.path).toBe('/otra')
  })
})
