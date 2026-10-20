<script setup lang="ts">
import { useId } from 'vue'
import { useField } from 'vee-validate'
import InputText from 'primevue/inputtext'

defineOptions({ inheritAttrs: false })
const props = withDefaults(
  defineProps<{
    nombre: string
    etiqueta: string
    ayuda?: string
    tipo?: 'text' | 'email' | 'password' | 'tel' | 'date' | 'month'
  }>(),
  { tipo: 'text' },
)
const id = useId()
const { value, errorMessage, handleBlur } = useField<string>(() => props.nombre)
</script>

<template>
  <div class="campo-texto">
    <label :for="id">{{ etiqueta }}</label>
    <InputText
      v-bind="$attrs"
      :id="id"
      v-model="value"
      :name="nombre"
      :type="tipo"
      :invalid="!!errorMessage"
      :aria-invalid="!!errorMessage"
      :aria-describedby="
        [ayuda ? `${id}-ayuda` : '', errorMessage ? `${id}-error` : ''].filter(Boolean).join(' ') ||
        undefined
      "
      @blur="handleBlur"
    />
    <small v-if="ayuda" :id="`${id}-ayuda`" class="ayuda">{{ ayuda }}</small>
    <small v-if="errorMessage" :id="`${id}-error`" role="alert" class="error">{{
      errorMessage
    }}</small>
  </div>
</template>

<style scoped>
.campo-texto {
  display: grid;
  gap: 8px;
  min-width: 0;
  color: var(--deconsta-ink);
}
label {
  font-weight: 600;
}
input {
  width: 100%;
  min-height: 44px;
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
