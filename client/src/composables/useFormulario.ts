import { computed, inject, onScopeDispose, ref } from 'vue'
import { useOnline } from '@vueuse/core'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { routerKey } from 'vue-router'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import type { AnyZodObject } from 'zod'
import type { ErrorApi } from '@/types/api'

export interface OpcionesFormulario {
  esquema: AnyZodObject
  valoresIniciales: Record<string, unknown>
  guardar: (valores: Record<string, unknown>) => Promise<unknown>
  mensajeExito?: string
}

export function useFormulario(opciones: OpcionesFormulario) {
  const formulario = useForm<Record<string, unknown>>({
    validationSchema: toTypedSchema(opciones.esquema),
    initialValues: opciones.valoresIniciales,
  })
  const online = useOnline()
  const aviso = ref('')
  const confirmacion = useConfirm()
  const toast = useToast()
  const router = inject(routerKey, null)
  const puedeGuardar = computed(
    () => online.value && formulario.meta.value.dirty && !formulario.isSubmitting.value,
  )
  const procesar = formulario.handleSubmit(async (valores) => {
    aviso.value = ''
    try {
      await opciones.guardar(valores)
      formulario.resetForm({ values: { ...valores } })
      toast.add({
        severity: 'success',
        summary: 'Guardado',
        detail: opciones.mensajeExito || 'Los cambios se guardaron.',
        life: 5000,
      })
    } catch (error: unknown) {
      const datos = error as Partial<ErrorApi> | null
      const detalle =
        typeof datos?.detail === 'string'
          ? datos.detail
          : 'No se pudo guardar. Conservamos lo escrito para que puedas reintentar.'
      if (
        typeof datos?.field === 'string' &&
        Object.prototype.hasOwnProperty.call(formulario.values, datos.field)
      ) {
        formulario.setFieldError(datos.field, detalle)
      } else {
        aviso.value = detalle
      }
    }
  })

  function enviar(event?: Event) {
    event?.preventDefault()
    if (!puedeGuardar.value) return
    return procesar(event)
  }

  function antesDeCerrar(event: BeforeUnloadEvent) {
    if (!formulario.meta.value.dirty) return
    event.preventDefault()
    event.returnValue = ''
  }
  window.addEventListener('beforeunload', antesDeCerrar)
  const quitarGuard = router?.beforeEach(() => {
    if (!formulario.meta.value.dirty) return true
    return new Promise<boolean>((resolve) => {
      confirmacion.require({
        header: 'Cambios sin guardar',
        message: 'Si sales, perderás los cambios de este formulario.',
        acceptLabel: 'Salir sin guardar',
        rejectLabel: 'Seguir editando',
        defaultFocus: 'reject',
        accept: () => resolve(true),
        reject: () => resolve(false),
        onHide: () => resolve(false),
      })
    })
  })
  onScopeDispose(() => {
    window.removeEventListener('beforeunload', antesDeCerrar)
    quitarGuard?.()
  })

  return { ...formulario, online, aviso, puedeGuardar, enviar }
}
