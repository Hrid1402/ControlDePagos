<script setup lang="ts">
import type { EstadoCuenta } from '@/types/asistentes'

// El estado se lee en el texto; el color solo lo refuerza (TASK-11).
defineProps<{ estado: EstadoCuenta }>()
</script>

<template>
  <span class="etiqueta" :class="estado">
    <span class="punto" aria-hidden="true"></span>{{ estado === 'activa' ? 'Activa' : 'Inactiva' }}
  </span>
</template>

<style scoped>
.etiqueta {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 3px 11px 3px 9px;
  border-radius: 999px;
  font-size: var(--texto-sm);
  font-weight: 600;
  white-space: nowrap;
}
.punto {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}
.activa {
  background: var(--deconsta-primary);
  color: var(--deconsta-paper);
}
.inactiva {
  border: 1px solid var(--deconsta-linea);
  color: var(--deconsta-muted);
}
</style>
