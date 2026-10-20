import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import { configuracionUi } from '@/config/ui'
import MiCuentaPage from '@/pages/MiCuentaPage.vue'
import { obtenerPerfil } from '@/api/acceso'
import type { PerfilCuenta } from '@/types/cuenta'

vi.mock('@/api/acceso', () => ({ obtenerPerfil: vi.fn<() => Promise<PerfilCuenta>>() }))
const cargarPerfil = vi.mocked(obtenerPerfil)

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
  politica_version: '1.0',
  politica_aceptada_en: '2026-10-01T10:00:00-05:00',
}
const montados: VueWrapper[] = []
beforeEach(() => {
  setActivePinia(createPinia())
  cargarPerfil.mockReset()
})
afterEach(() => {
  montados.splice(0).forEach((w) => w.unmount())
  document.body.innerHTML = ''
})

async function montar(perfil: Partial<PerfilCuenta> | Error = {}) {
  if (perfil instanceof Error) cargarPerfil.mockRejectedValueOnce(perfil)
  else cargarPerfil.mockResolvedValueOnce({ ...perfilBase, ...perfil })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/gerente/cuenta', component: MiCuentaPage }],
  })
  await router.push('/gerente/cuenta')
  await router.isReady()
  const wrapper = mount(MiCuentaPage, {
    attachTo: document.body,
    global: { plugins: [router, [PrimeVue, configuracionUi], ToastService, ConfirmationService] },
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

describe('Mi cuenta: resumen y carga', () => {
  it('muestra el perfil real con el rol solo de lectura y sin señales inventadas (CA09)', async () => {
    const wrapper = await montar()
    const resumen = wrapper.get('aside')
    expect(resumen.text()).toContain('Ana Rojas Peña')
    expect(resumen.text()).toContain('Gerente')
    expect(resumen.text()).toContain('ana.rojas')
    expect(resumen.text()).toContain('Completos')
    // La API aún no informa el contador ni la contraseña inicial: no se calculan en el cliente.
    expect(resumen.text()).toContain('Por confirmar')
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
    cargarPerfil.mockResolvedValueOnce(perfilBase)
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('Reintentar'))!
      .trigger('click')
    await flushPromises()
    expect(wrapper.get('aside').text()).toContain('Ana Rojas Peña')
  })

  it('sugiere cambiar la contraseña inicial cuando la API lo informa (CA18)', async () => {
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
    ['celular', '812345678', 'El celular tiene 9 dígitos y empieza con 9.'],
    ['numero_documento', '1234', 'El DNI tiene 8 dígitos.'],
  ])('valida %s junto al campo (CA01 a CA06)', async (campo, valor, mensaje) => {
    const wrapper = await montar()
    await escribir(wrapper, campo, valor)
    expect(seccion(wrapper, 'datos').text()).toContain(mensaje)
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

  it('guardar no simula un éxito: avisa, conserva lo escrito y permite descartar', async () => {
    const wrapper = await montar()
    await escribir(wrapper, 'celular', '912345678')
    await seccion(wrapper, 'datos').get('form').trigger('submit')
    await vi.waitFor(() =>
      expect(seccion(wrapper, 'datos').text()).toContain('Todavía no podemos guardar este cambio'),
    )
    expect(wrapper.get<HTMLInputElement>('[name="celular"]').element.value).toBe('912345678')
    await seccion(wrapper, 'datos')
      .findAll('button')
      .find((b) => b.text() === 'Descartar cambios')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[name="celular"]').element.value).toBe('987654321')
  })
})

describe('Mi cuenta: usuario', () => {
  it('sin el contador real el cambio espera y lo explica (CA07)', async () => {
    const wrapper = await montar()
    expect(seccion(wrapper, 'usuario').find('fieldset[disabled]').exists()).toBe(true)
    expect(seccion(wrapper, 'usuario').text()).toContain('cuando confirmemos cuántos cambios')
  })

  it('con cambios disponibles rechaza el mismo usuario aunque cambie las mayúsculas', async () => {
    const wrapper = await montar({ cambios_restantes: 2 })
    expect(seccion(wrapper, 'usuario').text()).toContain('Te quedan 2 cambios este mes.')
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
    await seccion(wrapper, 'contrasena').get('form').trigger('submit')
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
})
