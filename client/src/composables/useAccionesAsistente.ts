import { ref } from 'vue'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import {
  activarAsistente,
  desactivarAsistente,
  eliminarAsistente,
  restablecerContrasena,
} from '@/api/asistentes'
import { nombreDe, type AsistenteFila, type Credenciales } from '@/types/asistentes'
import type { ErrorApi } from '@/types/api'

interface Opciones {
  /** La cuenta activa del gerente, para nombrar a ambas al reemplazarla (CA10). */
  activaActual: () => AsistenteFila | null
  /** Vuelve a pedir el estado al servidor: tras cada cambio y ante un conflicto. */
  recargar: () => Promise<unknown> | void
  mostrarCredenciales: (credenciales: Credenciales) => void
  alEliminar?: () => void
}

const plural = (n: number, uno: string, varios: string) => (n === 1 ? uno : varios)

/** Acciones del ciclo de la cuenta (H03 CA10 a CA16) con su confirmación y su resultado. Una
 *  respuesta 409 nunca se toma como éxito: se informa y se recarga el estado actual. */
export function useAccionesAsistente(opciones: Opciones) {
  const confirmacion = useConfirm()
  const toast = useToast()
  const ocupada = ref<string | null>(null)

  function confirmar(datos: {
    titulo: string
    mensaje: string
    boton: string
    peligro?: boolean
    ejecutar: () => Promise<void>
  }) {
    confirmacion.require({
      header: datos.titulo,
      message: datos.mensaje,
      acceptLabel: datos.boton,
      rejectLabel: 'Cancelar',
      defaultFocus: 'reject',
      acceptProps: datos.peligro ? { severity: 'danger' } : undefined,
      rejectProps: { text: true },
      accept: () => void datos.ejecutar(),
    })
  }

  async function ejecutar(cuenta: AsistenteFila, accion: () => Promise<string | void>) {
    ocupada.value = cuenta.id
    try {
      const mensaje = await accion()
      if (mensaje) toast.add({ severity: 'success', summary: 'Listo', detail: mensaje, life: 6000 })
      await opciones.recargar()
    } catch (error: unknown) {
      const datos = error as Partial<ErrorApi> | null
      toast.add({
        severity: 'error',
        summary: datos?.status === 409 ? 'La cuenta cambió' : 'No se pudo completar',
        detail: datos?.detail || 'Revisa tu conexión e inténtalo otra vez.',
        life: 8000,
      })
      // Tras un conflicto o un resultado incierto, se muestra lo que hay en el servidor.
      await opciones.recargar()
    } finally {
      ocupada.value = null
    }
  }

  function activar(cuenta: AsistenteFila) {
    const nueva = nombreDe(cuenta)
    const actual = opciones.activaActual()
    confirmar({
      titulo: `Activar a ${nueva}`,
      mensaje: actual
        ? `Activar a ${nueva} desactivará a ${nombreDe(actual)} y cerrará su sesión. Las órdenes urgentes sin atender pasarán a ${nueva}.`
        : `${nueva} podrá atender los pagos a partir de ahora.`,
      boton: `Activar a ${nueva}`,
      ejecutar: () =>
        ejecutar(cuenta, async () => {
          const r = await activarAsistente(cuenta.id)
          const partes = [`${nueva} está activa.`]
          if (r.desactivada)
            partes.push(`${nombreDe(r.desactivada)} quedó inactiva y se cerró su sesión.`)
          const n = r.ordenes_traspasadas.length
          if (n)
            partes.push(
              `${n} ${plural(n, 'orden urgente pasó', 'órdenes urgentes pasaron')} a ${nueva}.`,
            )
          return partes.join(' ')
        }),
    })
  }

  function desactivar(cuenta: AsistenteFila) {
    const nombre = nombreDe(cuenta)
    confirmar({
      titulo: `Desactivar a ${nombre}`,
      mensaje: `${nombre} perderá el acceso. No quedará una asistente activa: tú atenderás los pagos. Las órdenes urgentes sin atender se cancelarán y recibirás un aviso.`,
      boton: `Desactivar a ${nombre}`,
      peligro: true,
      ejecutar: () =>
        ejecutar(cuenta, async () => {
          const r = await desactivarAsistente(cuenta.id)
          const partes = [`Se cerró la sesión de ${nombre}.`]
          if (r.aviso) partes.push(r.aviso)
          const n = r.ordenes_canceladas.length
          if (n)
            partes.push(
              `${n} ${plural(n, 'orden urgente se canceló', 'órdenes urgentes se cancelaron')}.`,
            )
          return partes.join(' ')
        }),
    })
  }

  function eliminar(cuenta: AsistenteFila) {
    const nombre = nombreDe(cuenta)
    confirmar({
      titulo: 'Eliminar cuenta',
      mensaje: `Eliminarás la cuenta de ${nombre}. Sus acciones conservarán su nombre en el historial.`,
      boton: 'Eliminar cuenta',
      peligro: true,
      ejecutar: () =>
        ejecutar(cuenta, async () => {
          await eliminarAsistente(cuenta.id)
          opciones.alEliminar?.()
          return `Eliminaste la cuenta de ${nombre}.`
        }),
    })
  }

  function restablecer(cuenta: AsistenteFila) {
    const nombre = nombreDe(cuenta)
    confirmar({
      titulo: 'Restablecer contraseña',
      mensaje: `Se generará una contraseña nueva para ${nombre} y se cerrarán todas sus sesiones.`,
      boton: 'Restablecer contraseña',
      ejecutar: () =>
        ejecutar(cuenta, async () => {
          opciones.mostrarCredenciales(await restablecerContrasena(cuenta))
          return `Se cerraron las sesiones de ${nombre}.`
        }),
    })
  }

  return { ocupada, activar, desactivar, eliminar, restablecer }
}
