<script setup lang="ts">
import { ref } from 'vue'
import CalendarioSuperficie from '@/components/calendario/CalendarioSuperficie.vue'

const estado = ref<'lista' | 'cargando' | 'error'>('lista')
</script>

<template>
  <div class="revision-calendario">
    <header class="borde">
      <img
        src="/brand/deconsta/logo/deconsta-wordmark-white.svg"
        alt="Deconsta"
        width="132"
        height="26"
      />
      <span>Revisión de diseño</span>
    </header>
    <main class="hoja">
      <CalendarioSuperficie :estado-pantalla="estado" @reintentar="estado = 'lista'" />
    </main>
    <div class="controles-revision">
      <label for="estado-revision">Estado de la pantalla</label>
      <select id="estado-revision" v-model="estado">
        <option value="lista">Sin vencimientos</option>
        <option value="cargando">Cargando</option>
        <option value="error">Error de conexión</option>
      </select>
      <p>Esta ruta solo existe en desarrollo. Los datos se conectan en TASK-59.</p>
    </div>
  </div>
</template>

<style scoped>
.revision-calendario {
  min-height: 100svh;
  padding: 0 var(--margen-mesa) var(--margen-mesa);
  background: var(--deconsta-primary);
}
.borde {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-height: 72px;
  color: var(--deconsta-sobre-mesa);
  font-size: var(--texto-sm);
}
.borde img {
  display: block;
  width: 132px;
  height: auto;
}
.hoja {
  min-height: calc(100svh - 140px);
  padding: clamp(24px, 4vw, 56px);
  border-radius: var(--radio-hoja);
  background: var(--deconsta-paper);
  color: var(--deconsta-ink);
}
.controles-revision {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 16px 4px 0;
  color: white;
  font-size: var(--texto-sm);
}
.controles-revision select {
  min-height: 40px;
  padding: 6px 10px;
  border: 1px solid var(--deconsta-sobre-mesa);
  border-radius: var(--radio-control);
  background: var(--deconsta-paper);
  color: var(--deconsta-ink);
}
.controles-revision p {
  margin: 0 0 0 auto;
  color: var(--deconsta-sobre-mesa);
}
@media (max-width: 767px) {
  .borde {
    min-height: 60px;
  }
  .hoja {
    min-height: calc(100svh - 150px);
    padding: 24px 20px 32px;
    border-radius: 5px 28px 5px 5px;
  }
  .controles-revision p {
    margin-left: 0;
  }
}
</style>
