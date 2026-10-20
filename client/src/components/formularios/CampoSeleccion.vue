<script setup lang="ts">
import { useId } from 'vue'
import { useField } from 'vee-validate'

defineOptions({ inheritAttrs: false })
const props = defineProps<{
  nombre: string
  etiqueta: string
  opciones: { valor: string; etiqueta: string }[]
  /** Texto de la opción vacía; sin él, el campo exige elegir. */
  vacia?: string
}>()
const id = useId()
const { value, errorMessage, handleBlur } = useField<string>(() => props.nombre)
</script>

<template>
  <div class="campo-seleccion">
    <label :for="id">{{ etiqueta }}</label>
    <div class="control">
      <select
        v-bind="$attrs"
        :id="id"
        v-model="value"
        :name="nombre"
        :aria-invalid="!!errorMessage"
        :aria-describedby="errorMessage ? `${id}-error` : undefined"
        @blur="handleBlur"
      >
        <option v-if="vacia !== undefined" value="">{{ vacia }}</option>
        <option v-for="opcion in opciones" :key="opcion.valor" :value="opcion.valor">
          {{ opcion.etiqueta }}
        </option>
      </select>
      <span class="pi pi-angle-down" aria-hidden="true"></span>
    </div>
    <small v-if="errorMessage" :id="`${id}-error`" role="alert" class="error">{{
      errorMessage
    }}</small>
  </div>
</template>

<style scoped>
.campo-seleccion {
  display: grid;
  gap: 8px;
  min-width: 0;
  color: var(--deconsta-ink);
}
label {
  font-weight: 600;
}
.control {
  position: relative;
}
/* Mismo aspecto que InputText del tema: borde, altura y foco. */
select {
  width: 100%;
  min-height: 44px;
  padding: 0 40px 0 12px;
  border: 1px solid #7b8798;
  border-radius: 6px;
  background: #fff;
  color: inherit;
  appearance: none;
  cursor: pointer;
}
select:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 2px;
  border-color: var(--deconsta-primary);
}
select[aria-invalid='true'] {
  border-color: var(--deconsta-error);
}
select:disabled {
  opacity: 0.6;
  cursor: default;
}
.pi {
  position: absolute;
  top: 50%;
  right: 14px;
  transform: translateY(-50%);
  font-size: 0.75rem;
  pointer-events: none;
}
small {
  font-size: 14px;
  line-height: 1.6;
}
.error {
  color: var(--deconsta-error);
}
</style>
