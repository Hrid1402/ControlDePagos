<script setup lang="ts">
import { inject, computed } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import { controlSesionKey } from '@/services/controlSesion'
const control = inject(controlSesionKey, null)
const tiempo = computed(() => {
  const segundos = control?.segundos.value || 0
  return `${Math.floor(segundos / 60)}:${String(segundos % 60).padStart(2, '0')}`
})
</script>
<template>
  <template v-if="control">
    <div
      v-if="
        control.error.value &&
        !control.advertencia.value &&
        control.sesion.confirmada === control.sesion.token
      "
      class="error-sesion"
      role="status"
    >
      {{ control.error.value }}
      <Button label="Reintentar" text @click="control.verificar(true).catch(() => {})" />
    </div>
    <Dialog
      :visible="control.advertencia.value"
      modal
      header="¿Seguimos trabajando?"
      :closable="false"
      :close-on-escape="false"
      :draggable="false"
      :style="{ width: 'min(440px, calc(100vw - 32px))' }"
    >
      <p>
        Tu sesión se cerrará por inactividad en <strong>{{ tiempo }}</strong
        >.
      </p>
      <p>Si continúas, conservarás lo que estás editando.</p>
      <p v-if="control.error.value" role="alert">{{ control.error.value }}</p>
      <template #footer>
        <Button label="Cerrar sesión" text @click="control.sesion.cerrar()" />
        <Button
          label="Continuar"
          autofocus
          :loading="control.renovando.value"
          @click="control.renovar(true)"
        />
      </template>
    </Dialog>
  </template>
</template>
<style scoped>
p {
  line-height: 1.6;
}
.error-sesion {
  position: fixed;
  top: 12px;
  left: 12px;
  right: 12px;
  max-width: 720px;
  margin: auto;
  z-index: 50;
  background: white;
  color: #192c29;
  padding: 12px 20px;
  border: 1px solid #075a50;
  border-radius: 12px;
}
</style>
