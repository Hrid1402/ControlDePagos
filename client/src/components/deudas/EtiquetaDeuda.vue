<script setup lang="ts">
import { computed } from 'vue'
import { estadoDe } from './estados'

// Estado de una deuda con su tono e ícono (H36 CA06). Los contrastes cumplen WCAG AA sobre el
// papel: el color acompaña al texto, nunca lo reemplaza.
const props = defineProps<{ estado: string; compacta?: boolean }>()
const descripcion = computed(() => estadoDe(props.estado))
</script>

<template>
  <span class="etiqueta" :class="[`tono-${descripcion.tono}`, { compacta }]">
    <i class="pi" :class="descripcion.icono" aria-hidden="true"></i>
    {{ descripcion.etiqueta }}
  </span>
</template>

<style scoped>
.etiqueta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: var(--texto-xs);
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
}
.etiqueta .pi {
  font-size: 0.75rem;
}
.compacta {
  padding: 2px 8px;
}
.tono-aviso {
  background: var(--deconsta-aviso-fondo);
  color: var(--deconsta-aviso);
}
.tono-peligro {
  background: var(--deconsta-error-fondo);
  color: var(--deconsta-error);
}
.tono-exito {
  background: #dff0e8;
  color: #135a42;
}
.tono-info {
  background: #e6edf5;
  color: #34506e;
}
.tono-proceso {
  background: #ebe8f5;
  color: #4a3d82;
}
.tono-neutro {
  background: var(--deconsta-realce);
  color: var(--deconsta-muted);
}
</style>
