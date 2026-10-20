<script setup lang="ts">
import { useId } from 'vue'
import { useField } from 'vee-validate'
import { LUGARES_PAGO } from './modelo'

// CA05: dónde se paga en persona. La asistente lo ve en la ruta de pagos.
const id = useId()
const { value, errorMessage } = useField<string>('lugar_pago')
</script>

<template>
  <fieldset class="lugares" :aria-describedby="errorMessage ? `${id}-error` : undefined">
    <legend>Dónde se paga</legend>
    <div class="opciones">
      <label v-for="l in LUGARES_PAGO" :key="l.valor" :class="{ elegido: value === l.valor }">
        <input v-model="value" type="radio" :name="`${id}-lugar`" :value="l.valor" />
        <i class="pi" :class="l.icono" aria-hidden="true"></i>
        <span>
          <span class="nombre">{{ l.etiqueta }}</span>
          <span v-if="l.nota" class="nota">{{ l.nota }}</span>
        </span>
      </label>
    </div>
    <small v-if="errorMessage" :id="`${id}-error`" role="alert" class="error">{{
      errorMessage
    }}</small>
  </fieldset>
</template>

<style scoped>
.lugares {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}
legend {
  margin-bottom: 8px;
  padding: 0;
  font-weight: 600;
}
.opciones {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 190px), 1fr));
  gap: 8px;
}
label {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-height: 52px;
  padding: 12px;
  border: 1px solid var(--deconsta-linea);
  border-radius: 4px 14px 4px 4px;
  background: var(--deconsta-paper-claro);
  cursor: pointer;
}
label.elegido {
  border-color: var(--deconsta-primary);
  box-shadow: inset 0 0 0 1px var(--deconsta-primary);
}
label:has(input:focus-visible) {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 2px;
}
/* El radio queda para teclado y lector; se ve el ícono del lugar. */
input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}
.pi {
  margin-top: 2px;
  color: var(--deconsta-primary);
}
.nombre {
  display: block;
  font-weight: 600;
}
.nota {
  display: block;
  margin-top: 2px;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.error {
  display: block;
  margin-top: 6px;
  color: var(--deconsta-error);
}
</style>
