<script setup lang="ts">
import { useSesionStore } from '@/stores/sesion'
const sesion = useSesionStore()
</script>
<template>
  <section aria-labelledby="inicio-titulo">
    <h1 id="inicio-titulo">Tu espacio, {{ sesion.usuario?.nombre }}.</h1>
    <p>
      Estamos preparando las herramientas para
      {{
        sesion.rol === 'gerente'
          ? 'autorizar y delegar tus pagos'
          : 'organizar los pagos que te asignen'
      }}.
    </p>
    <p class="nota">Aquí aparecerá tu trabajo cuando esté disponible.</p>
  </section>
</template>
<style scoped>
h1 {
  font-family: Literata, Georgia, serif;
  font-size: clamp(2rem, 5vw, 3.75rem);
  font-weight: 500;
  line-height: 1.2;
  max-width: 18ch;
  overflow-wrap: anywhere;
  margin: 0 0 28px;
}
p {
  max-width: 48ch;
  line-height: 1.7;
  font-size: 1.125rem;
}
.nota {
  margin-top: 48px;
  font-size: 0.875rem;
  color: var(--deconsta-muted);
}
</style>
