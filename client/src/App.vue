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
  <!-- El aviso no se lleva el foco: quien guarda con teclado sigue en su formulario. -->
  <Toast :close-button-props="{ autofocus: false }" />
  <ConfirmDialog />
</template>
