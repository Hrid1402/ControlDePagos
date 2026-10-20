import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import ConfirmDialog from 'primevue/confirmdialog'
import { z } from 'zod'
import { AxiosError } from 'axios'
import { rutas } from '@/router/rutas'
import { instalarAcceso } from '@/router/guard'
import { useSesionStore } from '@/stores/sesion'
import { crearHttp } from '@/api/http'
import { crearControlSesion, controlSesionKey, MINUTO } from '@/services/controlSesion'
import { configuracionUi } from '@/config/ui'
import FormularioBase from '@/components/formularios/FormularioBase.vue'
import CampoTexto from '@/components/formularios/CampoTexto.vue'
import EstadoSesion from '@/components/EstadoSesion.vue'
import EspacioLayout from '@/layouts/EspacioLayout.vue'

vi.mock('@/api/calendario', () => ({
  consultarCalendario: vi.fn().mockResolvedValue([]),
  listarCategoriasCalendario: vi.fn().mockResolvedValue([]),
  exportarCalendario: vi.fn(),
}))

const montados: VueWrapper[] = []
const limpiezas: (() => void)[] = []
const usuario = { id: '1', nombre: 'Ana', rol: 'gerente' as const }
const token = () =>
  `e30.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 1800 }))}.firma`
beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})
afterEach(() => {
  montados.splice(0).forEach((w) => w.unmount())
  limpiezas.splice(0).forEach((f) => f())
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function montar(
  rol: 'gerente' | 'asistente' = 'gerente',
  formulario = false,
  ruta?: string,
  sinRed = false,
) {
  const sesion = useSesionStore()
  sesion.iniciar(token(), { ...usuario, rol })
  const http = crearHttp({
    obtenerToken: () => sesion.token,
    alNoAutenticado: (e) => sesion.cerrar(e.code),
  })
  http.defaults.adapter = async (config) => {
    if (sinRed) throw new AxiosError('Sin red', 'ERR_NETWORK')
    return {
      data:
        config.url === '/auth/renovar'
          ? { access_token: token(), usuario: { ...usuario, rol } }
          : { ...usuario, rol },
      config,
      status: 200,
      headers: {},
      statusText: '',
    }
  }
  const control = crearControlSesion(sesion, http)
  const router = createRouter({ history: createMemoryHistory(), routes: rutas })
  if (formulario)
    router.addRoute({
      path: '/gerente/editar',
      component: EspacioLayout,
      children: [
        {
          path: '',
          component: defineComponent({
            setup: () => () =>
              h(
                FormularioBase,
                {
                  esquema: z.object({ nombre: z.string() }),
                  valoresIniciales: { nombre: '' },
                  guardar: async () => {},
                },
                { default: () => h(CampoTexto, { nombre: 'nombre', etiqueta: 'Nombre' }) },
              ),
          }),
        },
      ],
      meta: { rol: 'gerente' },
    })
  limpiezas.push(instalarAcceso(router, control), control.detener)
  await router.push(ruta || (formulario ? '/gerente/editar' : `/${rol}`))
  await router.isReady()
  const wrapper = mount(
    defineComponent({
      setup: () => () => h('div', [h(RouterView), h(ConfirmDialog), h(EstadoSesion)]),
    }),
    {
      attachTo: document.body,
      global: {
        plugins: [router, [PrimeVue, configuracionUi], ConfirmationService, ToastService],
        provide: { [controlSesionKey as symbol]: control },
      },
    },
  )
  montados.push(wrapper)
  await flushPromises()
  return { wrapper, router, control, sesion, http }
}
/** Abre el menú de la cuenta y elige una opción; el menú se monta fuera del componente. */
async function elegirEnCuenta(wrapper: VueWrapper, opcion: string) {
  await wrapper.get('button[aria-controls="menu-cuenta"]').trigger('click')
  await flushPromises()
  const item = [...document.querySelectorAll<HTMLElement>('#menu-cuenta [role="menuitem"]')].find(
    (e) => e.textContent?.includes(opcion),
  )!
  item.querySelector<HTMLElement>('.p-menu-item-content')!.click()
  await flushPromises()
}
describe('espacios y avisos de sesión', () => {
  it('ofrece reintentar tras un fallo de conexión y recupera la ruta autorizada', async () => {
    const { wrapper, router, http } = await montar(
      'gerente',
      false,
      '/login?motivo=sin-conexion&redirect=/gerente',
      true,
    )
    expect(wrapper.text()).toContain('No pudimos comprobar tu sesión')
    http.defaults.adapter = async (config) => ({
      data: usuario,
      config,
      status: 200,
      headers: {},
      statusText: '',
    })
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('Reintentar'))!
      .trigger('click')
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('gerente-inicio'))
  })

  it('confirma el cierre manual con cambios y permite seguir editando o descartarlos', async () => {
    const { wrapper, control, sesion, router } = await montar('gerente', true)
    await wrapper.get('input').setValue('Texto por guardar')
    expect(control.hayCambios()).toBe(true)
    await elegirEnCuenta(wrapper, 'Cerrar sesión')
    let dialogo = document.querySelector('[role="alertdialog"]')!
    expect(dialogo.textContent).toContain('perderás lo que estás editando')
    ;[...dialogo.querySelectorAll('button')]
      .find((b) => b.textContent?.includes('Seguir editando'))!
      .click()
    await flushPromises()
    expect(wrapper.get('input').element.value).toBe('Texto por guardar')
    await elegirEnCuenta(wrapper, 'Cerrar sesión')
    dialogo = document.querySelector('[role="alertdialog"]')!
    ;[...dialogo.querySelectorAll('button')]
      .find((b) => b.textContent?.includes('Cerrar sin guardar'))!
      .click()
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
    expect(sesion.token).toBeNull()
  })

  it.each([
    ['gerente', ['Panel', 'Deudas', 'Calendario', 'Órdenes', 'Servicios', 'Asistentes'], 'deudas'],
    ['asistente', ['Bandeja', 'Calendario', 'Ruta de pagos', 'Comprobantes'], 'calendario'],
  ] as const)(
    '%s: pestañas de su espacio, identidad visible y salida desde el menú de la cuenta',
    async (rol, etiquetas, segunda) => {
      const { wrapper, router, sesion } = await montar(rol)
      expect(wrapper.get('button[aria-controls="menu-cuenta"]').attributes('aria-label')).toContain(
        'Ana',
      )
      expect(wrapper.get('img').attributes('src')).toContain('wordmark-white.svg')
      const pestanas = wrapper.findAll('nav[aria-label="Secciones"] a').map((a) => a.text())
      expect(pestanas).toEqual(expect.arrayContaining([...etiquetas]))
      // La sección de inicio sin pantalla todavía lo dice; no muestra datos de ejemplo.
      expect(wrapper.get('main h1').text()).toBe(etiquetas[0])
      expect(wrapper.text()).toContain('Esta sección se habilitará')
      expect(wrapper.get('nav[aria-label="Secciones"] a.activa').text()).toBe(etiquetas[0])

      await wrapper.findAll('nav[aria-label="Secciones"] a')[1]!.trigger('click')
      await vi.waitFor(() => expect(router.currentRoute.value.name).toBe(`${rol}-${segunda}`))

      await elegirEnCuenta(wrapper, 'Mi cuenta')
      await vi.waitFor(() => expect(router.currentRoute.value.name).toBe(`${rol}-cuenta`))

      await elegirEnCuenta(wrapper, 'Cerrar sesión')
      expect(sesion.token).toBeNull()
      await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
    },
  )
  it('el gerente encuentra las secciones secundarias en Más y las ve como pestaña al abrirlas', async () => {
    const { wrapper, router } = await montar('gerente')
    await wrapper.get('button[aria-controls="secciones-mas"]').trigger('click')
    await flushPromises()
    const opciones = [...document.querySelectorAll('#secciones-mas [role="menuitem"]')].map((e) =>
      e.textContent?.trim(),
    )
    expect(opciones).toEqual(['Categorías', 'Límites', 'Historial'])
    document
      .querySelector<HTMLElement>(
        '#secciones-mas [role="menuitem"]:last-child .p-menu-item-content',
      )!
      .click()
    // Historial ya tiene pantalla propia, que se carga bajo demanda.
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('gerente-historial'))
    expect(wrapper.get('nav[aria-label="Secciones"] li.actual a').text()).toBe('Historial')
    expect(wrapper.get('button[aria-controls="secciones-mas"]').classes()).toContain('activa')
  })
  it('mantiene el formulario montado al continuar y permite el cierre forzoso sin confirmación bloqueante', async () => {
    const { wrapper, control, sesion, router } = await montar('gerente', true)
    await wrapper.get('input').setValue('Dato sin guardar')
    sesion.ultimaActividad = Date.now() - 28 * MINUTO
    control.comprobar()
    await flushPromises()
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain(
      '¿Seguimos trabajando?',
    )
    const continuar = [...document.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('Continuar'),
    )!
    continuar.click()
    await flushPromises()
    expect(wrapper.get('input').element.value).toBe('Dato sin guardar')
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    sesion.cerrar('SESION_REVOCADA')
    await flushPromises()
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(control.formularios.size).toBe(0)
  })
  it('muestra la marca en el acceso y una dirección inexistente con retorno', async () => {
    const { wrapper, router, sesion } = await montar('gerente', false, '/no-existe')
    expect(wrapper.get('h1').text()).toBe('No encontramos esa página.')
    sesion.cerrar()
    await router.push('/login?motivo=inactividad')
    await flushPromises()
    expect(wrapper.text()).toContain('30 minutos sin actividad')
    expect(wrapper.get('h1').text()).toBe('Todo en su lugar.')
  })
})
