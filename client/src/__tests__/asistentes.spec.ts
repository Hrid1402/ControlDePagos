import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import ConfirmDialog from 'primevue/confirmdialog'
import Toast from 'primevue/toast'
import { configuracionUi } from '@/config/ui'
import AsistentesPage from '@/pages/AsistentesPage.vue'
import AsistenteDetallePage from '@/pages/AsistenteDetallePage.vue'
import * as api from '@/api/asistentes'
import type { AsistenteDetalle, AsistenteFila } from '@/types/asistentes'

vi.mock('@/api/asistentes', () => ({
  listarAsistentes: vi.fn<typeof api.listarAsistentes>(),
  obtenerAsistente: vi.fn<typeof api.obtenerAsistente>(),
  consultarDisponibilidad: vi.fn<typeof api.consultarDisponibilidad>(),
  crearAsistente: vi.fn<typeof api.crearAsistente>(),
  activarAsistente: vi.fn<typeof api.activarAsistente>(),
  desactivarAsistente: vi.fn<typeof api.desactivarAsistente>(),
  eliminarAsistente: vi.fn<typeof api.eliminarAsistente>(),
  restablecerContrasena: vi.fn<typeof api.restablecerContrasena>(),
}))
const simulada = vi.mocked(api)

const fila = (id: string, nombres: string, estado: AsistenteFila['estado']): AsistenteFila => ({
  id,
  nombres,
  apellidos: 'Prueba',
  username: `${nombres.toLowerCase()}.prueba`,
  estado,
  ultimo_ingreso: null,
  creado_en: '2026-10-20T10:00:00-05:00',
})
const lucia = fila('a1', 'Lucía', 'activa')
const rosa = fila('a2', 'Rosa', 'inactiva')
const errorApi = (status: number, code: string, detail: string) => ({
  status,
  code,
  detail,
  field: null,
})

const montados: VueWrapper[] = []
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
})
afterEach(() => {
  montados.splice(0).forEach((w) => w.unmount())
  document.body.innerHTML = ''
})

async function montar(ruta = '/gerente/asistentes') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/gerente/asistentes', name: 'gerente-asistentes', component: AsistentesPage },
      {
        path: '/gerente/asistentes/:id',
        name: 'gerente-asistente',
        component: AsistenteDetallePage,
      },
    ],
  })
  await router.push(ruta)
  await router.isReady()
  const wrapper = mount(
    defineComponent({ setup: () => () => h('div', [h(RouterView), h(ConfirmDialog), h(Toast)]) }),
    {
      attachTo: document.body,
      global: {
        plugins: [router, [PrimeVue, configuracionUi], ToastService, ConfirmationService],
      },
    },
  )
  montados.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}
const confirmacion = () => document.querySelector<HTMLElement>('[role="alertdialog"]')
function botonEn(raiz: ParentNode | null, texto: string) {
  return [...(raiz?.querySelectorAll('button') ?? [])].find((b) =>
    b.textContent?.includes(texto),
  ) as HTMLButtonElement | undefined
}

describe('Lista de asistentes', () => {
  it('pone primero a quien atiende los pagos y distingue la activa con texto (CA01 y CA02)', async () => {
    simulada.listarAsistentes.mockResolvedValue([lucia, rosa])
    const { wrapper } = await montar()
    expect(wrapper.get('.turno').text()).toContain('Lucía Prueba atiende tus pagos')
    const filas = wrapper.findAll('tbody tr')
    expect(filas[0]!.classes()).toContain('es-activa')
    expect(filas[0]!.text()).toContain('Activa')
    expect(filas[0]!.text()).toContain('Aún no ingresó')
    expect(filas[1]!.text()).toContain('Inactiva')
    expect(botonEn(filas[1]!.element, 'Activar')).toBeDefined()
    expect(botonEn(filas[0]!.element, 'Activar')).toBeUndefined()
  })

  it('sin cuentas invita a crear la primera, con el botón del encabezado siempre visible (CA03)', async () => {
    simulada.listarAsistentes.mockResolvedValue([])
    const { wrapper } = await montar()
    expect(wrapper.text()).toContain('Todavía no tienes asistentes')
    expect(botonEn(wrapper.element, 'Crear primera asistente')).toBeDefined()
    expect(botonEn(wrapper.get('header').element, 'Crear asistente')).toBeDefined()
  })

  it('sin activa avisa que el gerente atenderá los pagos', async () => {
    simulada.listarAsistentes.mockResolvedValue([rosa])
    const { wrapper } = await montar()
    expect(wrapper.text()).toContain('No hay una asistente activa. Tú atenderás los pagos.')
    expect(wrapper.find('.turno').exists()).toBe(false)
  })

  it('si la carga falla no finge una lista vacía y permite reintentar', async () => {
    simulada.listarAsistentes.mockRejectedValueOnce(new Error('sin red'))
    const { wrapper } = await montar()
    expect(wrapper.text()).toContain('No pudimos cargar tus asistentes.')
    expect(wrapper.text()).not.toContain('Todavía no tienes asistentes')
    simulada.listarAsistentes.mockResolvedValueOnce([lucia])
    botonEn(wrapper.element, 'Reintentar')!.click()
    await flushPromises()
    expect(wrapper.find('tbody').text()).toContain('Lucía Prueba')
  })
})

describe('Crear asistente y credenciales', () => {
  async function abrirCreacion(cuentas: AsistenteFila[]) {
    simulada.listarAsistentes.mockResolvedValue(cuentas)
    const montaje = await montar()
    botonEn(montaje.wrapper.get('header').element, 'Crear asistente')!.click()
    await flushPromises()
    const dialogo = () => document.querySelector<HTMLElement>('[role="dialog"]')!
    const escribir = async (nombre: string, valor: string) => {
      const campo = dialogo().querySelector<HTMLInputElement>(`[name="${nombre}"]`)!
      campo.value = valor
      campo.dispatchEvent(new Event('input'))
      campo.dispatchEvent(new Event('blur'))
      await flushPromises()
    }
    return { ...montaje, dialogo, escribir }
  }

  it('con una activa crea la nueva inactiva sin reemplazarla y ofrece activarla (CA04, CA08 y CA09)', async () => {
    const { dialogo, escribir } = await abrirCreacion([lucia])
    expect(dialogo().textContent).toContain('Se creará inactiva, porque Lucía Prueba está activa')
    simulada.crearAsistente.mockResolvedValueOnce({
      id: 'a3',
      nombre: 'Ana Ruiz',
      username: 'ana.ruiz',
      contrasena: 'Secreta-2026!',
      estado: 'inactiva',
    })
    simulada.listarAsistentes.mockResolvedValue([lucia, fila('a3', 'Ana', 'inactiva')])
    await escribir('nombres', 'Ana')
    await escribir('apellidos', 'Ruiz')
    botonEn(dialogo(), 'Crear asistente inactiva')!.click()
    await vi.waitFor(() =>
      expect(simulada.crearAsistente).toHaveBeenCalledWith({
        nombres: 'Ana',
        apellidos: 'Ruiz',
        username: undefined,
        contrasena: undefined,
        activar_ahora: false,
      }),
    )
    await vi.waitFor(() => expect(dialogo().textContent).toContain('Credenciales de Ana Ruiz'))
    expect(dialogo().textContent).toContain('ana.ruiz')
    // La contraseña aparece oculta hasta pedirla.
    expect(dialogo().textContent).not.toContain('Secreta-2026!')
    botonEn(dialogo(), 'Mostrar')!.click()
    await flushPromises()
    expect(dialogo().textContent).toContain('Secreta-2026!')
    expect(botonEn(dialogo(), 'Activar ahora')).toBeDefined()
  })

  it('sin activa la crea y la activa en el mismo paso', async () => {
    const { dialogo, escribir } = await abrirCreacion([])
    simulada.crearAsistente.mockResolvedValueOnce({
      id: 'a3',
      nombre: 'Ana Ruiz',
      username: 'ana.ruiz',
      contrasena: 'Secreta-2026!',
      estado: 'activa',
    })
    await escribir('nombres', 'Ana')
    await escribir('apellidos', 'Ruiz')
    botonEn(dialogo(), 'Crear y activar')!.click()
    await vi.waitFor(() =>
      expect(simulada.crearAsistente.mock.calls[0]![0].activar_ahora).toBe(true),
    )
  })

  it('el usuario elegido se comprueba mientras se escribe y se puede usar la sugerencia (CA05 y CA06)', async () => {
    const { dialogo, escribir } = await abrirCreacion([])
    simulada.consultarDisponibilidad.mockResolvedValue({
      disponible: false,
      username: 'ana',
      sugerencia: 'ana1',
    })
    botonEn(dialogo(), 'Elegir')!.click()
    await flushPromises()
    await escribir('username', 'ana')
    await vi.waitFor(() => expect(dialogo().textContent).toContain('Ya está en uso.'), {
      timeout: 2000,
    })
    botonEn(dialogo(), 'Usar ana1')!.click()
    await flushPromises()
    expect(dialogo().querySelector<HTMLInputElement>('[name="username"]')!.value).toBe('ana1')
  })

  it('cerrar las credenciales pide confirmación porque la contraseña no vuelve a mostrarse', async () => {
    const { dialogo, escribir } = await abrirCreacion([])
    simulada.crearAsistente.mockResolvedValueOnce({
      id: 'a3',
      nombre: 'Ana Ruiz',
      username: 'ana.ruiz',
      contrasena: 'Secreta-2026!',
      estado: 'activa',
    })
    await escribir('nombres', 'Ana')
    await escribir('apellidos', 'Ruiz')
    botonEn(dialogo(), 'Crear y activar')!.click()
    await vi.waitFor(() => expect(dialogo().textContent).toContain('Credenciales de Ana Ruiz'))
    botonEn(dialogo(), 'Listo')!.click()
    await flushPromises()
    expect(confirmacion()?.textContent).toContain('no podrás volver a ver esta contraseña')
    botonEn(confirmacion(), 'Volver a credenciales')!.click()
    await flushPromises()
    expect(dialogo().textContent).toContain('Credenciales de Ana Ruiz')
    botonEn(dialogo(), 'Listo')!.click()
    await flushPromises()
    botonEn(confirmacion(), 'Cerrar de todas formas')!.click()
    await flushPromises()
    expect(document.body.textContent).not.toContain('Secreta-2026!')
    expect(document.querySelector('[role="dialog"]')).toBeNull()
  })
})

describe('Acciones sobre la cuenta', () => {
  it('activar nombra a ambas antes de cambiar y cuenta las órdenes traspasadas (CA10 y CA14)', async () => {
    simulada.listarAsistentes.mockResolvedValue([lucia, rosa])
    const { wrapper } = await montar()
    botonEn(wrapper.findAll('tbody tr')[1]!.element, 'Activar')!.click()
    await flushPromises()
    expect(confirmacion()!.textContent).toContain(
      'Activar a Rosa Prueba desactivará a Lucía Prueba',
    )
    simulada.activarAsistente.mockResolvedValueOnce({
      activada: { ...rosa, estado: 'activa' },
      desactivada: { ...lucia, estado: 'inactiva' },
      ordenes_traspasadas: ['o1', 'o2'],
    })
    botonEn(confirmacion(), 'Activar a Rosa Prueba')!.click()
    await vi.waitFor(() => expect(simulada.activarAsistente).toHaveBeenCalledWith('a2'))
    await vi.waitFor(() =>
      expect(document.body.textContent).toContain('2 órdenes urgentes pasaron a Rosa Prueba'),
    )
    expect(simulada.listarAsistentes).toHaveBeenCalledTimes(2)
  })

  it('el detalle muestra datos e historial y solo ofrece eliminar una inactiva (CA15 y CA17)', async () => {
    const detalle: AsistenteDetalle = {
      ...rosa,
      historial: [
        {
          accion: 'desactivada',
          realizada_por: 'Carla Vega',
          creado_en: '2026-10-20T12:00:00-05:00',
        },
        { accion: 'activada', realizada_por: 'Carla Vega', creado_en: '2026-10-19T12:00:00-05:00' },
      ],
    }
    simulada.obtenerAsistente.mockResolvedValue(detalle)
    simulada.listarAsistentes.mockResolvedValue([lucia, rosa])
    const { wrapper } = await montar('/gerente/asistentes/a2')
    expect(wrapper.get('h1').text()).toBe('Rosa Prueba')
    const historial = wrapper.findAll('.historial li').map((li) => li.text())
    expect(historial[0]).toContain('Desactivada')
    expect(historial[0]).toContain('por Carla Vega')
    expect(historial[1]).toContain('Activada')
    expect(botonEn(wrapper.element, 'Eliminar cuenta')).toBeDefined()

    simulada.obtenerAsistente.mockResolvedValue({ ...lucia, historial: [] })
    const activa = await montar('/gerente/asistentes/a1')
    expect(botonEn(activa.wrapper.element, 'Eliminar cuenta')).toBeUndefined()
    expect(activa.wrapper.text()).toContain('Todavía no hay cambios de estado registrados.')
  })

  it('una cuenta ajena o eliminada no muestra datos', async () => {
    simulada.obtenerAsistente.mockRejectedValue(
      errorApi(404, 'NO_ENCONTRADO', 'No se encontró el recurso solicitado.'),
    )
    simulada.listarAsistentes.mockResolvedValue([])
    const { wrapper } = await montar('/gerente/asistentes/ajena')
    expect(wrapper.text()).toContain('Cuenta no disponible')
    expect(wrapper.find('.historial').exists()).toBe(false)
  })

  it('un 409 no se toma como éxito: avisa y recarga el estado (CA11 y CA12)', async () => {
    simulada.obtenerAsistente.mockResolvedValue({ ...lucia, historial: [] })
    simulada.listarAsistentes.mockResolvedValue([lucia])
    const { wrapper } = await montar('/gerente/asistentes/a1')
    botonEn(wrapper.element, 'Desactivar')!.click()
    await flushPromises()
    expect(confirmacion()!.textContent).toContain('tú atenderás los pagos')
    simulada.desactivarAsistente.mockRejectedValueOnce(
      errorApi(409, 'CONFLICTO', 'La cuenta cambió mientras confirmabas.'),
    )
    botonEn(confirmacion(), 'Desactivar a Lucía Prueba')!.click()
    await vi.waitFor(() =>
      expect(document.body.textContent).toContain('La cuenta cambió mientras confirmabas.'),
    )
    expect(simulada.obtenerAsistente).toHaveBeenCalledTimes(2)
  })

  it('restablecer muestra la contraseña nueva una sola vez (CA16)', async () => {
    simulada.obtenerAsistente.mockResolvedValue({ ...rosa, historial: [] })
    simulada.listarAsistentes.mockResolvedValue([lucia, rosa])
    const { wrapper } = await montar('/gerente/asistentes/a2')
    botonEn(wrapper.element, 'Restablecer contraseña')!.click()
    await flushPromises()
    simulada.restablecerContrasena.mockResolvedValueOnce({
      id: 'a2',
      nombre: 'Rosa Prueba',
      username: 'rosa.prueba',
      contrasena: 'Nueva-2026!x',
    })
    botonEn(confirmacion(), 'Restablecer contraseña')!.click()
    await vi.waitFor(() =>
      expect(document.querySelector('[role="dialog"]')?.textContent).toContain(
        'Nueva contraseña de Rosa Prueba',
      ),
    )
    expect(document.body.textContent).toContain('Se cerraron las sesiones de Rosa Prueba')
  })
})
