<script setup lang="ts">
import { nextTick, ref } from 'vue'
import Button from 'primevue/button'
import Message from 'primevue/message'
import { useFormulario, type OpcionesFormulario } from '@/composables/useFormulario'

const props = defineProps<
  OpcionesFormulario & {
    textoBoton?: string
    /** Ofrece «Descartar cambios» mientras haya cambios sin guardar. */
    descartable?: boolean
    /** Desactiva campos y envío; quien lo usa explica el motivo junto al formulario. */
    bloqueado?: boolean
  }
>()
const { online, aviso, puedeGuardar, isSubmitting, enviar, meta, values, resetForm } =
  useFormulario(props)

// Mientras se guarda, el botón se desactiva y el navegador suelta el foco. Al terminar vuelve al
// botón que envió o, si sigue desactivado porque ya no hay cambios (RG05), al formulario: quien
// usa teclado o lector de pantalla sigue donde estaba.
const formulario = ref<HTMLFormElement>()
async function enviarConservandoFoco(event: Event) {
  const boton = (event as SubmitEvent).submitter
  await enviar(event)
  await nextTick()
  if (document.activeElement !== document.body) return
  if (boton instanceof HTMLButtonElement && !boton.disabled) boton.focus()
  else formulario.value?.focus()
}
</script>

<template>
  <form
    ref="formulario"
    class="formulario-base"
    tabindex="-1"
    novalidate
    :aria-busy="isSubmitting"
    @submit="enviarConservandoFoco"
  >
    <Message v-if="!online" severity="warn" :closable="false">
      No tienes conexión. Puedes seguir editando; conservaremos lo escrito mientras esta página esté
      abierta.
    </Message>
    <Message v-if="aviso" severity="error" :closable="false">{{ aviso }}</Message>
    <fieldset :disabled="isSubmitting || bloqueado">
      <slot :valores="values" />
    </fieldset>
    <div class="acciones">
      <Button
        type="submit"
        :label="isSubmitting ? 'Guardando…' : textoBoton || 'Guardar'"
        :loading="isSubmitting"
        :disabled="!puedeGuardar || bloqueado"
      />
      <Button
        v-if="descartable && meta.dirty && !isSubmitting"
        type="button"
        label="Descartar cambios"
        text
        @click="resetForm()"
      />
    </div>
  </form>
</template>

<style scoped>
.formulario-base {
  outline: none;
  display: grid;
  gap: 24px;
  width: 100%;
  max-width: 48rem;
  color: var(--deconsta-ink);
}
fieldset {
  display: grid;
  gap: 24px;
  min-width: 0;
  margin: 0;
  border: 0;
  padding: 0;
}
.acciones {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
}
.acciones :deep(button) {
  min-height: 44px;
}
@media (max-width: 640px) {
  .acciones :deep(button[type='submit']) {
    width: 100%;
  }
}
</style>
