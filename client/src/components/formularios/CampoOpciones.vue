<script setup lang="ts">
import { useId } from 'vue'
import { useField } from 'vee-validate'
import SelectButton from 'primevue/selectbutton'

// Elección entre pocas opciones excluyentes, visibles a la vez (por ejemplo, generar o elegir).
const props = defineProps<{
  nombre: string
  etiqueta: string
  opciones: { valor: string; etiqueta: string }[]
}>()
const id = useId()
const { value } = useField<string>(() => props.nombre)
</script>

<template>
  <div class="campo-opciones" role="group" :aria-labelledby="id">
    <span :id="id" class="etiqueta">{{ etiqueta }}</span>
    <SelectButton
      v-model="value"
      :options="opciones"
      option-label="etiqueta"
      option-value="valor"
      :allow-empty="false"
      :aria-labelledby="id"
    />
  </div>
</template>

<style scoped>
.campo-opciones {
  display: grid;
  gap: 8px;
  justify-items: start;
}
.etiqueta {
  font-weight: 600;
}
/* Colores de la marca en lugar del gris del tema: la opción elegida es verde Vínculo. */
.campo-opciones :deep(.p-selectbutton) {
  padding: 3px;
  border-radius: var(--radio-control);
  background: var(--deconsta-realce);
}
.campo-opciones :deep(.p-togglebutton) {
  min-height: 40px;
  padding: 0 18px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--deconsta-ink);
  font-weight: 600;
}
.campo-opciones :deep(.p-togglebutton .p-togglebutton-content) {
  background: transparent;
  box-shadow: none;
}
.campo-opciones :deep(.p-togglebutton.p-togglebutton-checked) {
  background: var(--deconsta-primary);
  color: var(--deconsta-paper);
}
.campo-opciones :deep(.p-togglebutton.p-togglebutton-checked .p-togglebutton-content) {
  color: var(--deconsta-paper);
}
</style>
