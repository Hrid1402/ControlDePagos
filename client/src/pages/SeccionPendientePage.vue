<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useSesionStore } from '@/stores/sesion'
import { SECCIONES, nombreRuta } from '@/config/navegacion'

// Toda sección del menú tiene su ruta desde ya; mientras su historia no tenga pantalla, aquí se
// explica qué hará, sin datos de ejemplo.
const route = useRoute()
const sesion = useSesionStore()
const primerNombre = computed(() => sesion.usuario?.nombre.split(/\s+/)[0] || '')
const esInicio = computed(() => String(route.name).endsWith('-inicio'))
const seccion = computed(() =>
  SECCIONES[sesion.rol || 'gerente'].find(
    (s) => nombreRuta(sesion.rol || 'gerente', s.clave) === route.name,
  ),
)
</script>

<template>
  <section class="pendiente" aria-labelledby="titulo-seccion">
    <p v-if="esInicio && primerNombre" class="saludo">Hola, {{ primerNombre }}.</p>
    <h1 id="titulo-seccion">{{ seccion?.etiqueta }}</h1>
    <p class="descripcion">{{ seccion?.descripcion }}</p>
    <p class="estado">Esta sección se habilitará cuando su historia esté terminada.</p>
  </section>
</template>

<style scoped>
.pendiente {
  max-width: 62ch;
}
.saludo {
  margin: 0 0 8px;
  color: var(--deconsta-muted);
  font-size: var(--texto-md);
}
h1 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-xl);
  font-weight: 500;
  letter-spacing: -0.02em;
  line-height: 1.15;
}
.descripcion {
  margin: 16px 0 0;
  font-size: var(--texto-md);
  line-height: 1.6;
}
.estado {
  margin: 40px 0 0;
  padding-left: 16px;
  border-left: 3px solid var(--deconsta-linea);
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  line-height: 1.6;
}
</style>
