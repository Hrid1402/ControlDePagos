<script setup lang="ts">
import { useId } from 'vue'
import { useField } from 'vee-validate'
import Textarea from 'primevue/textarea'

// CA06: instrucciones para quien paga, como «pedir boleta a nombre de la empresa».
const LARGO = 500
const id = useId()
const { value, errorMessage, handleBlur } = useField<string>('notas')
</script>

<template>
  <div class="campo-notas">
    <label :for="id">Notas para pagar <span class="opcional">(opcional)</span></label>
    <Textarea
      :id="id"
      v-model="value"
      name="notas"
      rows="3"
      auto-resize
      :maxlength="LARGO"
      :invalid="!!errorMessage"
      :aria-describedby="`${id}-cuenta`"
      @blur="handleBlur"
    />
    <small :id="`${id}-cuenta`" class="cuenta">{{ (value ?? '').length }} de {{ LARGO }}</small>
    <small v-if="errorMessage" role="alert" class="error">{{ errorMessage }}</small>
  </div>
</template>

<style scoped>
.campo-notas {
  display: grid;
  gap: 6px;
}
label {
  font-weight: 600;
}
.opcional {
  color: var(--deconsta-muted);
  font-weight: 400;
}
.cuenta {
  justify-self: end;
  color: var(--deconsta-muted);
  font-variant-numeric: tabular-nums;
}
.error {
  color: var(--deconsta-error);
}
</style>
