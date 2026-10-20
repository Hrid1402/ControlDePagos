<script setup lang="ts">
import { ref } from 'vue'
import CampoTexto from '@/components/formularios/CampoTexto.vue'
defineOptions({ inheritAttrs: false })
withDefaults(
  defineProps<{
    nombre: string
    etiqueta: string
    secreto?: boolean
    tipo?: 'text' | 'email' | 'tel'
  }>(),
  { secreto: false, tipo: 'text' },
)
const visible = ref(false)
</script>
<template>
  <div class="campo-acceso" :class="{ 'campo-acceso--secreto': secreto }">
    <CampoTexto
      v-bind="$attrs"
      :nombre="nombre"
      :etiqueta="etiqueta"
      :tipo="secreto ? (visible ? 'text' : 'password') : tipo"
    />
    <button
      v-if="secreto"
      type="button"
      class="ver-clave"
      :aria-label="`${visible ? 'Ocultar' : 'Mostrar'} ${etiqueta.toLowerCase()}`"
      :aria-pressed="visible"
      @click="visible = !visible"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
        <circle cx="12" cy="12" r="3" />
        <path v-if="visible" d="m4 3 16 18" />
      </svg>
    </button>
  </div>
</template>
<style scoped>
.campo-acceso {
  position: relative;
  min-width: 0;
}
.campo-acceso :deep(.campo-texto) {
  gap: 8px;
}
.campo-acceso :deep(label) {
  font-size: 14px;
  font-weight: 600;
}
.campo-acceso :deep(input) {
  background: transparent;
  color: #192c29;
  border: 0;
  border-bottom: 1px solid #82958e;
  border-radius: 0;
  box-shadow: none;
  min-height: 52px;
  font-family: inherit;
  font-size: 17px;
  padding: 10px 0;
}
.campo-acceso :deep(input::placeholder) {
  color: #52665f;
  opacity: 1;
}
.campo-acceso :deep(input:focus-visible) {
  outline: 3px solid #075a50;
  outline-offset: 3px;
}
.campo-acceso--secreto :deep(input) {
  padding-right: 50px;
}
.campo-acceso :deep(small) {
  font-size: 13px;
  line-height: 1.5;
}
.ver-clave {
  position: absolute;
  top: 28px;
  right: 0;
  width: 44px;
  height: 44px;
  background: transparent;
  color: #52665f;
  border: 0;
  border-radius: 5px;
  cursor: pointer;
}
.ver-clave svg {
  width: 22px;
  height: 22px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.5;
}
.ver-clave:focus-visible {
  outline: 3px solid #075a50;
}
</style>
