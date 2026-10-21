<script setup lang="ts">
import { computed } from 'vue'
import { z } from 'zod'
import Dialog from 'primevue/dialog'
import FormularioBase from '@/components/formularios/FormularioBase.vue'
import CampoTexto from '@/components/formularios/CampoTexto.vue'
import CampoMonto from './CampoMonto.vue'
import CampoRecibo from './CampoRecibo.vue'
import { RECIBO_MAXIMO, RECIBO_TIPOS } from './modelo'
import type { DetalleDeuda } from './detalle'

// H11 CA10: editar una deuda. Si espera su recibo, confirmar el monto la deja pendiente. Monto y
// moneda no cambian durante un pago en curso: el backend responde 409 y aquí se explica antes.
const props = defineProps<{
  deuda: DetalleDeuda
  guardar: (valores: Record<string, unknown>) => Promise<unknown>
}>()
const emit = defineEmits<{ cerrar: [] }>()

const MONTO = /^\d{1,10}(\.\d{1,2})?$/
const sinRecibo = computed(() => props.deuda.monto === null)
const enCurso = computed(() =>
  ['en_proceso', 'por_validar', 'esperando_aprobacion'].includes(props.deuda.estado),
)
const esquema = computed(() =>
  z
    .object({
      monto: z.string().trim(),
      fecha_vencimiento: z.string().min(1, 'Elige la fecha de vencimiento.'),
      numero_recibo: z.string().trim().max(60, 'Usa como máximo 60 caracteres.'),
      recibo: z.custom<File | null>(),
    })
    .superRefine((v, ctx) => {
      if (!v.monto && sinRecibo.value) return
      if (!MONTO.test(v.monto) || !(Number(v.monto) > 0))
        ctx.addIssue({
          code: 'custom',
          path: ['monto'],
          message: 'Escribe un monto mayor que cero, con hasta 2 decimales.',
        })
      if (v.recibo && !RECIBO_TIPOS.includes(v.recibo.type))
        ctx.addIssue({ code: 'custom', path: ['recibo'], message: 'Adjunta un PDF, JPG o PNG.' })
      else if (v.recibo && v.recibo.size > RECIBO_MAXIMO)
        ctx.addIssue({ code: 'custom', path: ['recibo'], message: 'El archivo pesa más de 10 MB.' })
    }),
)
const iniciales = computed(() => ({
  monto: props.deuda.monto ?? '',
  fecha_vencimiento: props.deuda.fecha_vencimiento,
  numero_recibo: props.deuda.numero_recibo ?? '',
  recibo: null as File | null,
}))
</script>

<template>
  <Dialog
    visible
    modal
    :header="sinRecibo ? 'Confirmar el monto del recibo' : 'Editar la deuda'"
    :draggable="false"
    :style="{ width: 'min(520px, calc(100vw - 24px))' }"
    @update:visible="emit('cerrar')"
  >
    <p v-if="sinRecibo" class="explica">
      Escribe el monto del recibo que llegó: la deuda queda lista para pagarse.
    </p>
    <p v-else-if="enCurso" class="explica aviso">
      Hay un pago en curso: el monto no se puede cambiar hasta que se resuelva.
    </p>
    <FormularioBase
      :esquema="esquema"
      :valores-iniciales="iniciales"
      :guardar="guardar"
      :texto-boton="sinRecibo ? 'Confirmar monto' : 'Guardar cambios'"
      mensaje-exito="La deuda se actualizó."
    >
      <div class="campos">
        <CampoMonto
          nombre="monto"
          :etiqueta="sinRecibo ? 'Monto del recibo' : 'Monto'"
          :moneda="deuda.moneda"
          :ayuda="
            deuda.monto_proyectado && sinRecibo
              ? `El mes anterior fue ${deuda.moneda} ${deuda.monto_proyectado}.`
              : undefined
          "
          destacado
        />
        <CampoTexto nombre="fecha_vencimiento" etiqueta="Vencimiento" tipo="date" />
        <CampoTexto nombre="numero_recibo" etiqueta="N.º de recibo (opcional)" />
        <CampoRecibo />
      </div>
    </FormularioBase>
  </Dialog>
</template>

<style scoped>
.explica {
  margin: 0 0 16px;
  color: var(--deconsta-muted);
  line-height: 1.5;
}
.explica.aviso {
  padding: 10px 12px;
  border-left: 3px solid var(--deconsta-aviso);
  background: var(--deconsta-aviso-fondo);
  color: var(--deconsta-aviso);
}
.campos {
  display: grid;
  gap: 16px;
}
</style>
