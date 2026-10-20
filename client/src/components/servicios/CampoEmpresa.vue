<script setup lang="ts">
import { computed, useId } from 'vue'
import { useField } from 'vee-validate'
import { GRUPOS_EMPRESA, OTRA_EMPRESA, type Empresa } from './modelo'

// CA01: empresas comunes agrupadas por servicio, y «Otra empresa» para escribirla a mano.
const props = defineProps<{ empresas: Empresa[] }>()
const id = useId()
const { value, errorMessage, handleBlur } = useField<string>('empresa')

const grupos = computed(() =>
  (Object.keys(GRUPOS_EMPRESA) as Empresa['tipo_servicio'][])
    .map((tipo) => ({
      etiqueta: GRUPOS_EMPRESA[tipo],
      empresas: props.empresas
        .filter((e) => e.tipo_servicio === tipo)
        .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')),
    }))
    .filter((g) => g.empresas.length),
)
</script>

<template>
  <div class="campo-empresa">
    <label :for="id">Empresa</label>
    <select
      :id="id"
      v-model="value"
      name="empresa"
      :aria-invalid="!!errorMessage"
      :aria-describedby="errorMessage ? `${id}-error` : undefined"
      @blur="handleBlur"
    >
      <option value="" disabled>Elige la empresa</option>
      <optgroup v-for="grupo in grupos" :key="grupo.etiqueta" :label="grupo.etiqueta">
        <option v-for="e in grupo.empresas" :key="e.id" :value="e.id">{{ e.nombre }}</option>
      </optgroup>
      <option :value="OTRA_EMPRESA">Otra empresa</option>
    </select>
    <small v-if="errorMessage" :id="`${id}-error`" role="alert" class="error">{{
      errorMessage
    }}</small>
  </div>
</template>

<style scoped>
.campo-empresa {
  display: grid;
  gap: 6px;
}
label {
  font-weight: 600;
}
select {
  width: 100%;
  min-height: 44px;
  padding: 0 12px;
  border: 1px solid var(--deconsta-linea);
  border-radius: var(--radio-control);
  background: #fff;
  color: var(--deconsta-ink);
  font: inherit;
}
select:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 1px;
}
select[aria-invalid='true'] {
  border-color: var(--deconsta-error);
}
.error {
  color: var(--deconsta-error);
}
</style>
