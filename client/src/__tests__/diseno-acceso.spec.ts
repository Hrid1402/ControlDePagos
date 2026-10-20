import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import { configuracionUi } from '@/config/ui'
import FormularioIngreso from '@/components/acceso/FormularioIngreso.vue'
import FormularioRecuperacion from '@/components/acceso/FormularioRecuperacion.vue'
import FormularioClave from '@/components/acceso/FormularioClave.vue'
const wrappers: VueWrapper[] = []
const montar = (
  componente: typeof FormularioIngreso | typeof FormularioRecuperacion | typeof FormularioClave,
) => {
  const wrapper = mount(componente, {
    attachTo: document.body,
    global: { plugins: [[PrimeVue, configuracionUi]] },
  })
  wrappers.push(wrapper)
  return wrapper
}
afterEach(() => {
  wrappers.splice(0).forEach((w) => w.unmount())
  document.body.innerHTML = ''
  vi.useRealTimers()
})
async function estabilizar() {
  await flushPromises()
  await new Promise((resolve) => setTimeout(resolve, 5))
  await flushPromises()
}
describe('diseño Vue de acceso', () => {
  it('marca campos vacíos, permite revelar contraseña y emite credenciales sin recortar la clave', async () => {
    const w = montar(FormularioIngreso)
    await w.get('form').trigger('submit')
    await estabilizar()
    expect(w.text()).toContain('Escribe tu usuario.')
    expect(w.text()).toContain('Escribe tu contraseña.')
    await w.get('input[name="username"]').setValue('  revision  ')
    await w.get('input[name="contrasena"]').setValue(' clave con espacios ')
    await w.get('button[aria-label="Mostrar contraseña"]').trigger('click')
    expect(w.get('input[name="contrasena"]').attributes('type')).toBe('text')
    await w.get('button[aria-label="Ocultar contraseña"]').trigger('click')
    await w.get('form').trigger('submit')
    await estabilizar()
    expect(w.emitted('enviar')).toEqual([
      [{ username: 'revision', contrasena: ' clave con espacios ' }],
    ])
  })
  it('impide enviar mientras carga sin borrar lo escrito', async () => {
    const w = montar(FormularioIngreso)
    await w.get('input[name="username"]').setValue('revision')
    await w.get('input[name="contrasena"]').setValue('clave')
    await w.setProps({ cargando: true })
    await w.get('form').trigger('submit')
    await estabilizar()
    expect(w.emitted('enviar')).toBeUndefined()
    expect((w.get('input[name="username"]').element as HTMLInputElement).value).toBe('revision')
    expect(w.get('fieldset').attributes('disabled')).toBeDefined()
  })
  it('valida el correo antes de pedir recuperación', async () => {
    const w = montar(FormularioRecuperacion)
    await w.get('input').setValue('sin-formato')
    await w.get('form').trigger('submit')
    await estabilizar()
    expect(w.text()).toContain('Escribe un correo válido.')
    expect(w.emitted('enviar')).toBeUndefined()
    await w.get('input').setValue('revision@example.org')
    await w.get('form').trigger('submit')
    await estabilizar()
    expect(w.emitted('enviar')).toEqual([['revision@example.org']])
  })
  it('exige coincidencia y requisitos antes de emitir la nueva clave', async () => {
    const w = montar(FormularioClave)
    await w.get('input[name="nueva"]').setValue('Revision2026!')
    await w.get('input[name="confirmar"]').setValue('otra')
    await w.get('form').trigger('submit')
    await estabilizar()
    expect(w.text()).toContain('Las contraseñas deben coincidir.')
    await w.get('input[name="confirmar"]').setValue('Revision2026!')
    await w.get('form').trigger('submit')
    await estabilizar()
    expect(w.emitted('enviar')).toEqual([['Revision2026!']])
  })
})
