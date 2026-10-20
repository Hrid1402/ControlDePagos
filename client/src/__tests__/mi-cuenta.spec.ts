import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import { configuracionUi } from '@/config/ui'
import MiCuentaPage from '@/pages/MiCuentaPage.vue'
import ModalPolitica from '@/components/cuenta/ModalPolitica.vue'
import * as api from '@/api/acceso'
import { useSesionStore } from '@/stores/sesion'
import type { PerfilCuenta, PoliticaPrivacidad } from '@/types/cuenta'

vi.mock('@/api/acceso', () => ({
  obtenerPerfil: vi.fn<typeof api.obtenerPerfil>(),
  actualizarPerfil: vi.fn<typeof api.actualizarPerfil>(),
  cambiarUsuario: vi.fn<typeof api.cambiarUsuario>(),
  cambiarContrasena: vi.fn<typeof api.cambiarContrasena>(),
  obtenerPolitica: vi.fn<typeof api.obtenerPolitica>(),
  aceptarPolitica: vi.fn<typeof api.aceptarPolitica>(),
}))
const simulada = vi.mocked(api)

const perfilBase: PerfilCuenta = {
  id: 'u1',
  username: 'ana.rojas',
  rol: 'gerente',
  nombres: 'Ana',
  apellidos: 'Rojas Peña',
  tipo_documento: 'dni',
  numero_documento: '12345678',
  correo: 'ana@correo.pe',
  celular: '987654321',
  politica_version: '2026-10',
  politica_aceptada_en: '2026-10-01T10:00:00-05:00',
  cambios_restantes: 2,
  contrasena_inicial: false,
  politica_vigente: '2026-10',
}
const jwt = () => `e30.${btoa(JSON.stringify({ exp: Date.now() / 1000 + 1800 }))}.firma`
const errorApi = (status: number, code: string, detail: string, field: string | null) => ({
  status,
  code,
  detail,
  field,
})
const montados: VueWrapper[] = []
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  localStorage.clear()
})
afterEach(() => {
  montados.splice(0).forEach((w) => w.unmount())
  document.body.innerHTML = ''
})

const plugins = () => [
  [PrimeVue, configuracionUi] as [typeof PrimeVue, typeof configuracionUi],
  ToastService,
  ConfirmationService,
]
async function montar(perfil: Partial<PerfilCuenta> | Error = {}) {
  if (perfil instanceof Error) simulada.obtenerPerfil.mockRejectedValueOnce(perfil)
  else simulada.obtenerPerfil.mockResolvedValueOnce({ ...perfilBase, ...perfil })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/gerente/cuenta', component: MiCuentaPage }],
  })
  await router.push('/gerente/cuenta')
  await router.isReady()
  const wrapper = mount(MiCuentaPage, {
    attachTo: document.body,
    global: { plugins: [router, ...plugins()] },
  })
  montados.push(wrapper)
  await flushPromises()
  return wrapper
}
const seccion = (wrapper: VueWrapper, id: string) => wrapper.get(`#${id}`)
async function escribir(wrapper: VueWrapper, nombre: string, valor: string) {
  const campo = wrapper.get(`[name="${nombre}"]`)
  await campo.setValue(valor)
  await campo.trigger('blur')
  await flushPromises()
}
async function enviar(wrapper: VueWrapper, id: string) {
  await seccion(wrapper, id).get('form').trigger('submit')
  await flushPromises()
}

describe('Mi cuenta: resumen y carga', () => {
  it('muestra el perfil real con el rol solo de lectura y las señales de la API (CA09)', async () => {
    const wrapper = await montar()
    const resumen = wrapper.get('aside')
    expect(resumen.text()).toContain('Ana Rojas Peña')
    expect(resumen.text()).toContain('Gerente')
    expect(resumen.text()).toContain('ana.rojas')
    expect(resumen.text()).toContain('Completos')
    expect(resumen.text()).toContain('Quedan 2 este mes')
    expect(wrapper.text()).not.toContain('contraseña inicial')
    expect(wrapper.find('[name="rol"]').exists()).toBe(false)
    expect(wrapper.get<HTMLInputElement>('[name="nombres"]').element.value).toBe('Ana')
  })

  it('un perfil incompleto se muestra vacío y avisa qué falta, sin datos de ejemplo', async () => {
    const wrapper = await montar({ correo: null, celular: null, tipo_documento: null })
    expect(wrapper.get('aside').text()).toContain('Faltan 2 por completar')
    expect(seccion(wrapper, 'datos').text()).toContain('Completa tus datos personales')
    expect(wrapper.get<HTMLInputElement>('[name="celular"]').element.value).toBe('')
  })

  it('si la carga falla no muestra datos y permite reintentar', async () => {
    const wrapper = await montar(new Error('sin red'))
    expect(wrapper.text()).toContain('No pudimos cargar tu cuenta')
    expect(wrapper.find('aside').exists()).toBe(false)
    simulada.obtenerPerfil.mockResolvedValueOnce(perfilBase)
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('Reintentar'))!
      .trigger('click')
    await flushPromises()
    expect(wrapper.get('aside').text()).toContain('Ana Rojas Peña')
  })

  it('sugiere cambiar la contraseña inicial (CA18)', async () => {
    const wrapper = await montar({ contrasena_inicial: true })
    const sugerencia = wrapper.get('.sugerencia')
    expect(sugerencia.text()).toContain('Aún usas la contraseña inicial')
    expect(sugerencia.get('a').attributes('href')).toBe('#contrasena')
  })
})

describe('Mi cuenta: datos personales', () => {
  it.each([
    ['nombres', 'Ana2', 'Usa solo letras, con tildes y ñ.'],
    ['correo', 'ana@', 'Revisa el formato del correo.'],
    ['correo', '', 'Escribe tu correo.'],
    ['celular', '812345678', 'El celular tiene 9 dígitos y empieza con 9.'],
    ['numero_documento', '1234', 'El DNI tiene 8 dígitos.'],
  ])('valida %s junto al campo (CA01 a CA06)', async (campo, valor, mensaje) => {
    const wrapper = await montar()
    await escribir(wrapper, campo, valor)
    await vi.waitFor(() => expect(seccion(wrapper, 'datos').text()).toContain(mensaje))
  })

  it('el carné de extranjería admite de 9 a 12 caracteres (CA03)', async () => {
    const wrapper = await montar()
    await wrapper.get('[name="tipo_documento"]').setValue('ce')
    await escribir(wrapper, 'numero_documento', '12345678')
    await vi.waitFor(() =>
      expect(seccion(wrapper, 'datos').text()).toContain('de 9 a 12 letras o números'),
    )
    await escribir(wrapper, 'numero_documento', 'AB1234567')
    await vi.waitFor(() =>
      expect(seccion(wrapper, 'datos').text()).not.toContain('de 9 a 12 letras o números'),
    )
  })

  it('guarda, se reconcilia con el servidor y actualiza el nombre de la sesión', async () => {
    const sesion = useSesionStore()
    sesion.iniciar(jwt(), { id: 'u1', rol: 'gerente', nombre: 'Ana Rojas Peña' })
    const wrapper = await montar({ tipo_documento: null, numero_documento: null })
    simulada.actualizarPerfil.mockResolvedValueOnce({
      ...perfilBase,
      nombres: 'Ana María',
      tipo_documento: null,
      numero_documento: null,
    })
    await escribir(wrapper, 'nombres', 'Ana María')
    await enviar(wrapper, 'datos')
    await vi.waitFor(() => expect(simulada.actualizarPerfil).toHaveBeenCalledOnce())
    // Sin documento se envía null: el servidor no admite el texto vacío.
    expect(simulada.actualizarPerfil.mock.calls[0]![0]).toMatchObject({
      nombres: 'Ana María',
      tipo_documento: null,
      numero_documento: null,
    })
    await vi.waitFor(() => expect(wrapper.get('aside').text()).toContain('Ana María Rojas Peña'))
    expect(sesion.usuario?.nombre).toBe('Ana María Rojas Peña')
    // El foco no se pierde al desactivarse el botón mientras guarda.
    await vi.waitFor(() =>
      expect(seccion(wrapper, 'datos').element.contains(document.activeElement)).toBe(true),
    )
  })

  it('un correo repetido se muestra junto al campo y conserva lo escrito (CA05)', async () => {
    const wrapper = await montar()
    simulada.actualizarPerfil.mockRejectedValueOnce(
      errorApi(409, 'CORREO_DUPLICADO', 'Ya existe un usuario con este correo.', 'correo'),
    )
    await escribir(wrapper, 'correo', 'otra@correo.pe')
    await enviar(wrapper, 'datos')
    await vi.waitFor(() =>
      expect(seccion(wrapper, 'datos').text()).toContain('Ya existe un usuario con este correo.'),
    )
    expect(wrapper.get<HTMLInputElement>('[name="correo"]').element.value).toBe('otra@correo.pe')
    await seccion(wrapper, 'datos')
      .findAll('button')
      .find((b) => b.text() === 'Descartar cambios')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[name="correo"]').element.value).toBe('ana@correo.pe')
  })
})

describe('Mi cuenta: usuario', () => {
  it('cambia el usuario y actualiza el contador del mes (CA07 y CA08)', async () => {
    const wrapper = await montar()
    expect(seccion(wrapper, 'usuario').text()).toContain('Te quedan 2 cambios este mes.')
    simulada.cambiarUsuario.mockResolvedValueOnce({
      username: 'ana.nueva',
      cambios_restantes: 1,
      aviso: 'Desde ahora debes ingresar con tu nuevo usuario.',
    })
    await escribir(wrapper, 'username', 'ana.nueva')
    await enviar(wrapper, 'usuario')
    await vi.waitFor(() => expect(simulada.cambiarUsuario).toHaveBeenCalledWith('ana.nueva'))
    await vi.waitFor(() =>
      expect(seccion(wrapper, 'usuario').text()).toContain('Te queda 1 cambio este mes.'),
    )
    expect(seccion(wrapper, 'usuario').text()).toContain('Ingresas como ana.nueva')
  })

  it('rechaza el mismo usuario aunque cambie las mayúsculas', async () => {
    const wrapper = await montar()
    expect(seccion(wrapper, 'usuario').find('fieldset[disabled]').exists()).toBe(false)
    await escribir(wrapper, 'username', 'Ana.Rojas')
    await vi.waitFor(() =>
      expect(seccion(wrapper, 'usuario').text()).toContain('El nuevo usuario es igual al actual.'),
    )
  })

  it('con los cambios agotados bloquea el campo e indica desde cuándo podrá cambiarlo', async () => {
    const wrapper = await montar({ cambios_restantes: 0 })
    expect(seccion(wrapper, 'usuario').find('fieldset[disabled]').exists()).toBe(true)
    expect(seccion(wrapper, 'usuario').text()).toContain('Podrás cambiarlo otra vez desde el 1')
    expect(wrapper.get('aside').text()).toContain('Sin cambios este mes')
  })
})

describe('Mi cuenta: contraseña', () => {
  it('pide la actual, confirma la nueva y marca cada requisito (CA12, CA13 y CA15)', async () => {
    const wrapper = await montar()
    await escribir(wrapper, 'contrasena_nueva', 'Deconsta2026')
    await escribir(wrapper, 'confirmacion', 'Deconsta20')
    await enviar(wrapper, 'contrasena')
    await vi.waitFor(() => {
      const texto = seccion(wrapper, 'contrasena').text()
      expect(texto).toContain('Escribe tu contraseña actual.')
      expect(texto).toContain('Las contraseñas no coinciden.')
    })
    const cumplidos = seccion(wrapper, 'contrasena')
      .findAll('li.cumple')
      .map((li) => li.text())
    expect(cumplidos.join(' ')).not.toContain('Símbolo')
    expect(cumplidos).toHaveLength(4)
  })

  it('la seguridad no llega a Fuerte si falta un requisito (CA14)', async () => {
    const wrapper = await montar()
    expect(wrapper.get('.nivel').text()).toBe('Escríbela para ver su seguridad.')
    await escribir(wrapper, 'contrasena_nueva', 'Deconsta2026')
    expect(wrapper.get('.nivel').text()).toBe('Seguridad: Media')
    await escribir(wrapper, 'contrasena_nueva', 'Deconsta2026!x')
    expect(wrapper.get('.nivel').text()).toBe('Seguridad: Fuerte')
    await escribir(wrapper, 'contrasena_nueva', 'abc')
    expect(wrapper.get('.nivel').text()).toBe('Seguridad: Débil')
  })

  async function llenarContrasena(wrapper: VueWrapper) {
    await escribir(wrapper, 'contrasena_actual', 'Actual-2026')
    await escribir(wrapper, 'contrasena_nueva', 'Nueva-Clave-2026')
    await escribir(wrapper, 'confirmacion', 'Nueva-Clave-2026')
    await enviar(wrapper, 'contrasena')
  }

  it('al cambiarla conserva esta sesión con el token renovado (CA17 y CA18)', async () => {
    const sesion = useSesionStore()
    sesion.iniciar(jwt(), { id: 'u1', rol: 'gerente', nombre: 'Ana Rojas Peña' })
    const wrapper = await montar({ contrasena_inicial: true })
    const renovado = jwt().replace('firma', 'renovada')
    simulada.cambiarContrasena.mockResolvedValueOnce({
      token: renovado,
      usuario: { id: 'u1', rol: 'gerente', nombre: 'Ana Rojas Peña' },
    })
    await llenarContrasena(wrapper)
    await vi.waitFor(() =>
      expect(simulada.cambiarContrasena).toHaveBeenCalledWith('Actual-2026', 'Nueva-Clave-2026'),
    )
    await vi.waitFor(() => expect(sesion.token).toBe(renovado))
    expect(wrapper.find('.sugerencia').exists()).toBe(false)
    // Los tres campos se vacían al terminar: la contraseña no queda en pantalla.
    for (const campo of ['contrasena_actual', 'contrasena_nueva', 'confirmacion'])
      expect(wrapper.get<HTMLInputElement>(`[name="${campo}"]`).element.value).toBe('')
  })

  it.each([
    ['CONTRASENA_INCORRECTA', 'La contraseña actual no es correcta.', 'contrasena_actual'],
    ['CONTRASENA_REPETIDA', 'No puede ser igual a las últimas 3.', 'contrasena_nueva'],
  ])(
    'muestra %s junto a su campo y no toca la sesión (CA12 y CA16)',
    async (code, detail, campo) => {
      const sesion = useSesionStore()
      const token = jwt()
      sesion.iniciar(token, { id: 'u1', rol: 'gerente', nombre: 'Ana Rojas Peña' })
      const wrapper = await montar()
      simulada.cambiarContrasena.mockRejectedValueOnce(errorApi(422, code, detail, campo))
      await llenarContrasena(wrapper)
      await vi.waitFor(() => expect(seccion(wrapper, 'contrasena').text()).toContain(detail))
      const error = wrapper.get(`[name="${campo}"]`).attributes('aria-describedby')
      expect(error).toContain('error')
      expect(sesion.token).toBe(token)
    },
  )
})

describe('Política de privacidad (CA10)', () => {
  const politica: PoliticaPrivacidad = {
    version: '2026-10',
    vigente_desde: '2026-10-20',
    secciones: [
      { titulo: 'Quién trata tus datos', parrafos: ['El responsable es Deconsta.'] },
      { titulo: 'Tus derechos', parrafos: ['Puedes pedir acceso.'] },
    ],
  }
  function montarModal() {
    const wrapper = mount(ModalPolitica, {
      attachTo: document.body,
      global: { plugins: plugins() },
    })
    montados.push(wrapper)
    return wrapper
  }
  const dialogo = () => document.querySelector<HTMLElement>('[role="dialog"]')!
  const boton = (texto: string) =>
    [...dialogo().querySelectorAll('button')].find((b) => b.textContent?.includes(texto))!

  it('muestra la versión vigente y no se cierra sin aceptar', async () => {
    simulada.obtenerPolitica.mockResolvedValueOnce(politica)
    const wrapper = montarModal()
    await flushPromises()
    expect(dialogo().textContent).toContain('Versión 2026-10, vigente desde el 20 de octubre')
    expect(dialogo().textContent).toContain('Quién trata tus datos')
    expect(dialogo().querySelector('[aria-label="Close"], .p-dialog-close-button')).toBeNull()
    dialogo().dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(dialogo()).not.toBeNull()
    boton('Cerrar sesión').click()
    expect(wrapper.emitted('salir')).toHaveLength(1)
  })

  it('acepta la versión mostrada y avisa con el perfil del servidor', async () => {
    simulada.obtenerPolitica.mockResolvedValueOnce(politica)
    simulada.aceptarPolitica.mockResolvedValueOnce({ ...perfilBase })
    const wrapper = montarModal()
    await flushPromises()
    boton('Aceptar y continuar').click()
    await flushPromises()
    expect(simulada.aceptarPolitica).toHaveBeenCalledWith('2026-10')
    expect(wrapper.emitted('aceptada')?.[0]).toEqual([perfilBase])
  })

  it('si la política cambió mientras se leía, carga la nueva y no la da por aceptada', async () => {
    simulada.obtenerPolitica
      .mockResolvedValueOnce(politica)
      .mockResolvedValueOnce({ ...politica, version: '2026-11' })
    simulada.aceptarPolitica.mockRejectedValueOnce(
      errorApi(409, 'POLITICA_DESACTUALIZADA', 'La política cambió.', 'version'),
    )
    const wrapper = montarModal()
    await flushPromises()
    boton('Aceptar y continuar').click()
    await flushPromises()
    expect(wrapper.emitted('aceptada')).toBeUndefined()
    expect(dialogo().textContent).toContain('La política cambió mientras la leías')
    expect(dialogo().textContent).toContain('Versión 2026-11')
  })

  it('si no carga, permite reintentar y no deja aceptar', async () => {
    simulada.obtenerPolitica.mockRejectedValueOnce(new Error('sin red'))
    montarModal()
    await flushPromises()
    expect(dialogo().textContent).toContain('No pudimos cargar la política')
    expect(boton('Aceptar y continuar').disabled).toBe(true)
  })
})
