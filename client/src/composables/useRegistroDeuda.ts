import { ref } from 'vue'
import { useToast } from 'primevue/usetoast'
import { configurarRecurrencia, crearPrestamo, registrarDeuda, subirRecibo } from '@/api/deudas'
import type { DatosDeuda, DeudaExistente } from '@/components/deudas/modelo'
import type { ErrorApi } from '@/types/api'

/**
 * Registro de una deuda según el tipo de su servicio (H11, TASK-41):
 * - préstamo: POST /prestamos crea todas sus cuotas (CA07);
 * - el resto: POST /deudas, con los datos de tarjeta si los tiene (CA06). Si se pidió repetirla,
 *   configura la recurrencia del servicio (CA04 y CA05) y, si trae recibo, lo adjunta (CA08).
 *
 * La deuda es lo principal: si ella se registró pero la recurrencia o el recibo fallan, no se
 * vuelve a enviar el formulario (duplicaría la deuda); se avisa qué faltó para hacerlo después.
 */
export function useRegistroDeuda(alRegistrar: () => unknown) {
  const toast = useToast()
  const duplicada = ref<DeudaExistente | null>(null)
  const dia = (fecha: string | null) => (fecha ? Number(fecha.slice(8)) : null)

  async function registrar(datos: DatosDeuda) {
    duplicada.value = null
    if (datos.tipo === 'prestamo') {
      await crearPrestamo(datos)
      await alRegistrar()
      return
    }
    let id: string
    try {
      ;({ id } = await registrarDeuda(datos))
    } catch (fallo) {
      const error = fallo as ErrorApi
      if (error.code === 'DUPLICADO' && error.datos?.deuda_existente)
        duplicada.value = error.datos.deuda_existente as DeudaExistente
      throw fallo
    }
    const pendientes: string[] = []
    if (datos.repetir) {
      try {
        await configurarRecurrencia(datos.servicio_id, {
          monto: datos.tipo === 'monto_fijo' ? datos.monto : null,
          moneda: datos.moneda,
          dia_emision: dia(datos.fecha_emision),
          dia_vencimiento: dia(datos.fecha_vencimiento) ?? 1,
          activa: true,
        })
      } catch {
        pendientes.push('dejarla programada cada mes')
      }
    }
    if (datos.recibo) {
      try {
        await subirRecibo(id, datos.recibo)
      } catch {
        pendientes.push('adjuntar el recibo')
      }
    }
    if (pendientes.length)
      toast.add({
        severity: 'warn',
        summary: 'La deuda se registró',
        detail: `Pero no se pudo ${pendientes.join(' ni ')}. Inténtalo desde su detalle.`,
        life: 8000,
      })
    await alRegistrar()
  }

  return { registrar, duplicada }
}
