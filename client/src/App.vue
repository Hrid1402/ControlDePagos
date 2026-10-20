<script setup lang="ts">
import { RouterView } from 'vue-router'
import { defineAsyncComponent, inject } from 'vue'
import { controlSesionKey } from './services/controlSesion'
import Toast from 'primevue/toast'
import ConfirmDialog from 'primevue/confirmdialog'

const control = inject(controlSesionKey, null)
const EstadoSesion = defineAsyncComponent(() => import('./components/EstadoSesion.vue'))
</script>

<template>
  <RouterView />
  <EstadoSesion v-if="control?.sesion.token" />
  <Toast />
  <ConfirmDialog />
</template>
