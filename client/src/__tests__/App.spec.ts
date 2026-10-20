import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import App from '../App.vue'
import ProntoPage from '../pages/ProntoPage.vue'
import { configuracionUi } from '../config/ui'

describe('portada de Deconsta', () => {
  it('conserva la marca al integrar los servicios comunes', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: ProntoPage }],
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(App, {
      global: { plugins: [router, [PrimeVue, configuracionUi], ToastService, ConfirmationService] },
    })
    expect(wrapper.get('h1').text()).toBe('Pronto estaremos disponibles.')
    expect(wrapper.get('img[alt="Deconsta"]').attributes('src')).toContain(
      'deconsta-wordmark-white.svg',
    )
    wrapper.unmount()
  })
})
