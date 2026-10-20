<script setup lang="ts">
import Button from 'primevue/button'
import Message from 'primevue/message'
import { useFormulario, type OpcionesFormulario } from '@/composables/useFormulario'

const props = defineProps<OpcionesFormulario & { textoBoton?: string }>()
const { online, aviso, puedeGuardar, isSubmitting, enviar } = useFormulario(props)
</script>

<template>
  <form class="formulario-base" novalidate :aria-busy="isSubmitting" @submit="enviar">
    <Message v-if="!online" severity="warn" :closable="false">
      No tienes conexión. Puedes seguir editando; conservaremos lo escrito mientras esta página esté
      abierta.
    </Message>
    <Message v-if="aviso" severity="error" :closable="false">{{ aviso }}</Message>
    <fieldset :disabled="isSubmitting">
      <slot />
    </fieldset>
    <Button
      type="submit"
      :label="textoBoton || 'Guardar'"
      :loading="isSubmitting"
      :disabled="!puedeGuardar"
    />
  </form>
</template>

<style scoped>
.formulario-base {
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
.formulario-base > button {
  justify-self: start;
  min-height: 44px;
}
</style>
