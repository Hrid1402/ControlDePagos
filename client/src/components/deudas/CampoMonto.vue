<script setup lang="ts">
import { useId } from 'vue'
import { useField } from 'vee-validate'
import { simbolo, type Moneda } from './modelo'

// Monto con el símbolo de la moneda delante (CA09). Se escribe como texto: nunca se convierte a
// número para no perder céntimos.
const props = defineProps<{
  nombre: string
  etiqueta: string
  moneda: Moneda | string
  ayuda?: string
  destacado?: boolean
}>()
const id = useId()
const { value, errorMessage, handleBlur } = useField<string>(() => props.nombre)
</script>

<template>
  <div class="campo-monto" :class="{ destacado }">
    <label :for="id">{{ etiqueta }}</label>
    <div class="caja" :class="{ invalido: !!errorMessage }">
      <span class="simbolo" aria-hidden="true">{{ simbolo(moneda) }}</span>
      <input
        :id="id"
        v-model="value"
        :name="nombre"
        inputmode="decimal"
        autocomplete="off"
        placeholder="0.00"
        :aria-invalid="!!errorMessage"
        :aria-describedby="
          [ayuda ? `${id}-ayuda` : '', errorMessage ? `${id}-error` : '']
            .filter(Boolean)
            .join(' ') || undefined
        "
        @blur="handleBlur"
      />
    </div>
    <small v-if="ayuda" :id="`${id}-ayuda`" class="ayuda">{{ ayuda }}</small>
    <small v-if="errorMessage" :id="`${id}-error`" role="alert" class="error">{{
      errorMessage
    }}</small>
  </div>
</template>

<style scoped>
.campo-monto {
  display: grid;
  gap: 8px;
  min-width: 0;
}
label {
  font-weight: 600;
}
.caja {
  display: flex;
  align-items: stretch;
  min-height: 44px;
  border: 1px solid var(--deconsta-linea);
  border-radius: var(--radio-control);
  background: #fff;
  overflow: hidden;
}
.caja:focus-within {
  border-color: var(--deconsta-primary);
  box-shadow: 0 0 0 1px var(--deconsta-primary);
}
.caja.invalido {
  border-color: var(--deconsta-error);
}
.simbolo {
  display: grid;
  place-items: center;
  min-width: 48px;
  padding: 0 10px;
  border-right: 1px solid var(--deconsta-linea);
  background: var(--deconsta-paper);
  color: var(--deconsta-muted);
  font-weight: 700;
  font-size: var(--texto-sm);
}
input {
  flex: 1;
  min-width: 0;
  padding: 0 12px;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--deconsta-ink);
  font: inherit;
  font-variant-numeric: tabular-nums;
  text-align: right;
}
/* El monto que se va a pagar se lee primero: más grande y en la tipografía de los títulos. */
.destacado input {
  font-family: Literata, Georgia, serif;
  font-size: 1.375rem;
}
.destacado .caja {
  min-height: 52px;
}
small {
  line-height: 1.6;
  font-size: 14px;
}
.ayuda {
  color: var(--deconsta-muted);
}
.error {
  color: #922838;
}
</style>
