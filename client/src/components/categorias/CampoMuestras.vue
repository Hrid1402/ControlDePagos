<script setup lang="ts">
import { useId } from 'vue'
import { useField } from 'vee-validate'

// Elección visual entre muestras (colores o íconos) con radios nativos: se recorren con las
// flechas y el lector anuncia el nombre de cada muestra, no solo lo que se ve.
const props = defineProps<{
  nombre: string
  etiqueta: string
  variante: 'color' | 'icono'
  opciones: { valor: string; etiqueta: string }[]
  /** Color de fondo de las muestras de ícono, para verlas como quedarán. */
  fondo?: string
  tinta?: string
}>()
const id = useId()
const { value, errorMessage } = useField<string>(() => props.nombre)
</script>

<template>
  <fieldset class="muestras" :aria-describedby="errorMessage ? `${id}-error` : undefined">
    <legend>{{ etiqueta }}</legend>
    <div class="opciones" :class="variante">
      <label
        v-for="opcion in opciones"
        :key="opcion.valor"
        class="muestra"
        :class="{ elegida: value === opcion.valor }"
        :title="opcion.etiqueta"
        :style="
          variante === 'color' ? { background: opcion.valor } : { background: fondo, color: tinta }
        "
      >
        <input
          v-model="value"
          type="radio"
          :name="`${id}-${nombre}`"
          :value="opcion.valor"
          class="lector"
        />
        <i v-if="variante === 'icono'" class="pi" :class="opcion.valor" aria-hidden="true"></i>
        <span class="lector">{{ opcion.etiqueta }}</span>
      </label>
    </div>
    <p v-if="errorMessage" :id="`${id}-error`" class="error">{{ errorMessage }}</p>
  </fieldset>
</template>

<style scoped>
.muestras {
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
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.muestra {
  position: relative;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 4px 12px 4px 4px;
  cursor: pointer;
  box-shadow: inset 0 0 0 1px rgb(0 0 0 / 0.08);
}
.icono .muestra {
  width: 40px;
  height: 40px;
  font-size: 1rem;
}
/* La elegida lleva un anillo de la tinta del papel y otro de la marca: se ve sobre cualquier color. */
.muestra.elegida {
  box-shadow:
    0 0 0 2px var(--deconsta-paper),
    0 0 0 4px var(--deconsta-primary);
}
.muestra:has(input:focus-visible) {
  outline: 2px dashed var(--deconsta-ink);
  outline-offset: 5px;
}
.error {
  margin: 6px 0 0;
  color: var(--deconsta-error);
  font-size: var(--texto-sm);
}
.lector {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
