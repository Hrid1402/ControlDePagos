import { afterEach, describe, it, expect, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import App from '../App.vue'
import { rutas } from '@/router/rutas'
import { configuracionUi } from '../config/ui'

let wrapper: VueWrapper | undefined
afterEach(() => {
  wrapper?.unmount()
  vi.restoreAllMocks()
})
async function abrir(ruta = '/') {
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  const router = createRouter({ history: createMemoryHistory(), routes: rutas })
  await router.push(ruta)
  await router.isReady()
  wrapper = mount(App, {
    global: { plugins: [router, [PrimeVue, configuracionUi], ToastService, ConfirmationService] },
  })
  return { router, pagina: wrapper }
}
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
  it('permite recuperar y volver sin anunciar un envío que todavía no ocurrió', async () => {
    const { pagina, router } = await abrir('/recuperar')
    await pagina.get('input').setValue('revision@example.org')
    await pagina.get('form').trigger('submit')
    await vi.waitFor(() => expect(pagina.text()).toContain('Esta opción estará disponible pronto.'))
    expect(router.currentRoute.value.name).toBe('recuperar')
    expect(pagina.text()).not.toContain('Revisa tu correo.')
    await pagina
      .findAll('button')
      .find((b) => b.text().includes('Volver al acceso'))!
      .trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/')
  })
  it('ofrece retorno al acceso desde una página sin permiso', async () => {
    const { pagina, router } = await abrir('/sin-permiso')
    expect(pagina.get('h1').text()).toBe('Este espacio no es el tuyo.')
    await pagina.get('.boton-acceso').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/')
  })
})
