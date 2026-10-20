<script setup lang="ts">
import { useId } from 'vue'
import { useField } from 'vee-validate'

// Sí o no con una explicación debajo, que se lee como parte de la opción.
const props = defineProps<{ nombre: string; etiqueta: string; ayuda?: string }>()
const id = useId()
const { value, handleChange } = useField<boolean>(() => props.nombre, undefined, {
  type: 'checkbox',
  checkedValue: true,
  uncheckedValue: false,
})
</script>

<template>
  <label class="campo-casilla" :class="{ marcada: value }">
    <input
      type="checkbox"
      :name="nombre"
      :checked="!!value"
      :aria-describedby="ayuda ? `${id}-ayuda` : undefined"
      @change="handleChange(($event.target as HTMLInputElement).checked)"
    />
    <span>
      <span class="etiqueta">{{ etiqueta }}</span>
      <small v-if="ayuda" :id="`${id}-ayuda`">{{ ayuda }}</small>
    </span>
  </label>
</template>

<style scoped>
.campo-casilla {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--deconsta-linea);
  border-radius: 4px 14px 4px 4px;
  background: var(--deconsta-paper-claro);
  cursor: pointer;
}
.campo-casilla.marcada {
  border-color: var(--deconsta-primary);
  box-shadow: inset 0 0 0 1px var(--deconsta-primary);
}
input {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  margin: 2px 0 0;
  accent-color: var(--deconsta-primary);
}
.etiqueta {
  display: block;
  font-weight: 600;
}
small {
  display: block;
  margin-top: 2px;
  color: var(--deconsta-muted);
  font-size: 14px;
  line-height: 1.5;
}
</style>
