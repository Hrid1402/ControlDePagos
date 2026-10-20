import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import { configuracionUi } from '@/config/ui'
import FormularioIngreso from '@/components/acceso/FormularioIngreso.vue'
import FormularioRecuperacion from '@/components/acceso/FormularioRecuperacion.vue'
import FormularioClave from '@/components/acceso/FormularioClave.vue'
import { esquemaUsername, motivoContrasena } from '@/config/reglas'
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
  it('pide el usuario, no el correo, y lo valida con la regla común antes de recuperar', async () => {
    const w = montar(FormularioRecuperacion)
    const campo = w.get('input[name="username"]')
    expect(campo.attributes('autocomplete')).toBe('username')
    expect(w.text()).toContain('Usuario')
    expect(w.find('input[type="email"]').exists()).toBe(false)
    await w.get('form').trigger('submit')
    await estabilizar()
    expect(w.text()).toContain('Escribe tu usuario.')
    await campo.setValue('dos palabras')
    await w.get('form').trigger('submit')
    await estabilizar()
    expect(w.text()).toContain('solo puede tener letras sin tilde')
    expect(w.emitted('enviar')).toBeUndefined()
    await campo.setValue('  Ana.Paz  ')
    await w.get('form').trigger('submit')
    await estabilizar()
    expect(w.emitted('enviar')).toEqual([['Ana.Paz']])
  })
  it('muestra en el campo el error que devuelve el servidor y le da el foco', async () => {
    const w = montar(FormularioRecuperacion)
    ;(w.vm as unknown as { marcarError: (m: string) => void }).marcarError('Usuario no válido.')
    await estabilizar()
    expect(w.text()).toContain('Usuario no válido.')
    expect(document.activeElement).toBe(w.get('input[name="username"]').element)
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
  it('muestra el motivo de servidor en la nueva contraseña y enfoca el campo', async () => {
    const w = montar(FormularioClave)
    ;(w.vm as unknown as { marcarError: (c: string, m: string) => void }).marcarError(
      'nueva',
      'No puede ser igual a las últimas 3.',
    )
    await estabilizar()
    expect(w.text()).toContain('No puede ser igual a las últimas 3.')
    expect(document.activeElement).toBe(w.get('input[name="nueva"]').element)
  })
})

// Mismos casos límite que server/tests/test_reglas.py.
describe('reglas de usuario y contraseña (copia de las del server)', () => {
  it.each(['Clave-segura-1', 'Aa1.aaaa', 'Ñandú#2026', 'Con espacio 1!', 'Aa1-'.repeat(18)])(
    'acepta la contraseña %s',
    (contrasena) => expect(motivoContrasena(contrasena)).toBeNull(),
  )
  it.each([
    ['Aa1-aaa', 'al menos 8'],
    ['clave-segura-1', 'mayúscula'],
    ['CLAVE-SEGURA-1', 'mayúscula'],
    ['Clave-segura', 'mayúscula'],
    ['ClaveSegura1', 'mayúscula'],
    ['Clave segura 1', 'mayúscula'],
    ['Aa1-'.repeat(18) + 'a', 'demasiado larga'],
    // 52 caracteres pero 78 bytes: el límite se cuenta en bytes.
    ['Ññ1-'.repeat(13), 'demasiado larga'],
  ])('rechaza %s con su motivo', (contrasena, motivo) => {
    const razon = motivoContrasena(contrasena)
    expect(razon).toContain(motivo)
    expect(razon).not.toContain(contrasena)
  })
  it.each(['abc', 'a'.repeat(30), 'ana.paz', 'j_perez-2', '  con_bordes  '])(
    'acepta el usuario %j recortando los bordes',
    (username) => expect(esquemaUsername.parse(username)).toBe(username.trim()),
  )
  it.each(['ab', 'a'.repeat(31), 'dos palabras', 'ñandu', 'a@b.com', ''])(
    'rechaza el usuario %j',
    (username) => expect(esquemaUsername.safeParse(username).success).toBe(false),
  )
})
