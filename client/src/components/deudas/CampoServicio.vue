<script setup lang="ts">
import { computed, useId } from 'vue'
import { useField } from 'vee-validate'
import { etiquetaTipo } from '@/components/categorias/modelo'
import type { Servicio } from '@/components/servicios/modelo'

// Servicios activos agrupados por categoría: elegir uno decide qué pide el formulario.
const props = defineProps<{ servicios: Servicio[] }>()
const id = useId()
const { value, errorMessage, handleBlur } = useField<string>('servicio_id')

const grupos = computed(() => {
  const porCategoria = new Map<string, { etiqueta: string; servicios: Servicio[] }>()
  for (const s of props.servicios.filter((x) => x.estado === 'activo')) {
    const grupo = porCategoria.get(s.categoria.id) ?? {
      etiqueta: `${s.categoria.nombre} · ${etiquetaTipo(s.categoria.tipo)}`,
      servicios: [],
    }
    grupo.servicios.push(s)
    porCategoria.set(s.categoria.id, grupo)
  }
  return [...porCategoria.values()].sort((a, b) => a.etiqueta.localeCompare(b.etiqueta, 'es'))
})
</script>

<template>
  <div class="campo-servicio">
    <label :for="id">Servicio</label>
    <select
      :id="id"
      v-model="value"
      name="servicio_id"
      :aria-invalid="!!errorMessage"
      :aria-describedby="errorMessage ? `${id}-error` : undefined"
      @blur="handleBlur"
    >
      <option value="" disabled>Elige el servicio</option>
      <optgroup v-for="g in grupos" :key="g.etiqueta" :label="g.etiqueta">
        <option v-for="s in g.servicios" :key="s.id" :value="s.id">
          {{ s.alias ? `${s.alias} — ` : '' }}{{ s.empresa }} {{ s.codigo_suministro }}
        </option>
      </optgroup>
    </select>
    <small v-if="errorMessage" :id="`${id}-error`" role="alert" class="error">{{
      errorMessage
    }}</small>
  </div>
</template>

<style scoped>
.campo-servicio {
  display: grid;
  gap: 8px;
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
  color: #922838;
  font-size: 14px;
}
</style>
