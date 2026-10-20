<script setup lang="ts">
import { ref, useId } from 'vue'
import { useField } from 'vee-validate'

// CA08: el recibo es opcional, en PDF o imagen. Se elige o se suelta aquí; se sube al guardar.
const id = useId()
const { value, errorMessage, setValue } = useField<File | null>('recibo')
const entrada = ref<HTMLInputElement>()
const encima = ref(false)

function elegir(archivos: FileList | null | undefined) {
  setValue(archivos?.[0] ?? null)
  encima.value = false
}
function quitar() {
  setValue(null)
  if (entrada.value) entrada.value.value = ''
}
const peso = (bytes: number) =>
  bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / 1048576).toFixed(1)} MB`
</script>

<template>
  <div class="campo-recibo">
    <span :id="`${id}-etiqueta`" class="etiqueta"
      >Recibo <span class="opcional">(opcional)</span></span
    >
    <div v-if="value" class="elegido">
      <i
        class="pi"
        :class="value.type === 'application/pdf' ? 'pi-file-pdf' : 'pi-image'"
        aria-hidden="true"
      ></i>
      <span class="nombre">{{ value.name }}</span>
      <span class="peso">{{ peso(value.size) }}</span>
      <button type="button" :aria-label="`Quitar ${value.name}`" @click="quitar">Quitar</button>
    </div>
    <label
      v-else
      class="zona"
      :class="{ encima }"
      @dragover.prevent="encima = true"
      @dragleave="encima = false"
      @drop.prevent="elegir($event.dataTransfer?.files)"
    >
      <input
        ref="entrada"
        type="file"
        name="recibo"
        accept="application/pdf,image/jpeg,image/png,image/webp"
        :aria-labelledby="`${id}-etiqueta`"
        :aria-describedby="errorMessage ? `${id}-error` : `${id}-ayuda`"
        @change="elegir(($event.target as HTMLInputElement).files)"
      />
      <i class="pi pi-upload" aria-hidden="true"></i>
      <span>
        <strong>Elige el archivo</strong> o suéltalo aquí
        <small :id="`${id}-ayuda`">PDF o imagen, hasta 10 MB.</small>
      </span>
    </label>
    <small v-if="errorMessage" :id="`${id}-error`" role="alert" class="error">{{
      errorMessage
    }}</small>
  </div>
</template>

<style scoped>
.campo-recibo {
  display: grid;
  gap: 8px;
}
.etiqueta {
  font-weight: 600;
}
.opcional {
  color: var(--deconsta-muted);
  font-weight: 400;
}
.zona {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border: 1px dashed var(--deconsta-muted);
  border-radius: 4px 14px 4px 4px;
  background: var(--deconsta-paper-claro);
  cursor: pointer;
}
.zona.encima,
.zona:hover {
  border-color: var(--deconsta-primary);
  background: #fff;
}
.zona:has(input:focus-visible) {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 2px;
}
.zona input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.zona .pi {
  color: var(--deconsta-primary);
  font-size: 1.25rem;
}
.zona strong {
  color: var(--deconsta-primary);
}
.zona small {
  display: block;
  color: var(--deconsta-muted);
  font-size: 13px;
}
.elegido {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 52px;
  padding: 0 4px 0 14px;
  border: 1px solid var(--deconsta-linea);
  border-radius: 4px 14px 4px 4px;
  background: #fff;
}
.elegido .pi {
  color: var(--deconsta-primary);
}
.nombre {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.peso {
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  font-variant-numeric: tabular-nums;
}
.elegido button {
  min-height: 40px;
  padding: 0 10px;
  border: 0;
  background: transparent;
  color: var(--deconsta-error);
  font: inherit;
  font-size: var(--texto-sm);
  font-weight: 600;
  cursor: pointer;
}
.elegido button:focus-visible {
  outline: 2px solid currentColor;
}
.error {
  color: #922838;
  font-size: 14px;
}
</style>
