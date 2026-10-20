<script setup lang="ts">
withDefaults(defineProps<{ compacto?: boolean }>(), {
  compacto: false,
})
const emit = defineEmits<{ inicio: [] }>()
</script>
<template>
  <div class="marco-acceso" :class="{ 'marco-acceso--compacto': compacto }">
    <a class="saltar-contenido" href="#contenido-acceso">Ir al contenido</a>
    <div class="marca-acceso">
      <a href="#" aria-label="Deconsta, volver al acceso" @click.prevent="emit('inicio')">
        <img
          src="/brand/deconsta/logo/deconsta-wordmark-white.svg"
          alt="Deconsta"
          width="188"
          height="37"
        />
      </a>
      <slot name="salida" />
    </div>
    <main id="contenido-acceso" tabindex="-1"><slot /></main>
    <footer class="firma-acceso">
      <p>Autoriza. Delega. Deja constancia.</p>
      <slot name="pie"><p>Un espacio para tus pagos.</p></slot>
    </footer>
  </div>
</template>
<style scoped>
.marco-acceso {
  --acceso-verde: #075a50;
  --acceso-papel: #f1f4f1;
  --acceso-tinta: #192c29;
  --acceso-tenue: #52665f;
  box-sizing: border-box;
  background: var(--acceso-verde);
  color: var(--acceso-papel);
  min-height: 100svh;
  width: 100%;
  padding: clamp(24px, 3vw, 48px) clamp(24px, 4vw, 64px) 26px;
  display: grid;
  grid-template-rows: auto 1fr auto;
  gap: clamp(20px, 3vh, 32px);
}
.marco-acceso--compacto {
  height: 100svh;
}
.marca-acceso {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-width: 0;
}
.marca-acceso a {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  flex-shrink: 0;
}
.marca-acceso img {
  width: clamp(144px, 15vw, 188px);
  height: auto;
  display: block;
}
main {
  display: flex;
  flex-direction: column;
  min-height: 0;
  width: 100%;
  max-width: 1552px;
  margin-inline: auto;
  outline: none;
}
.firma-acceso {
  font-size: 12px;
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  line-height: 1.5;
}
p {
  margin: 0;
}
a:focus-visible {
  outline: 3px solid currentColor;
  outline-offset: 6px;
}
.saltar-contenido {
  position: fixed;
  top: -100px;
  left: 20px;
  z-index: 100;
  padding: 16px;
  background: white;
  color: #075a50;
}
.saltar-contenido:focus {
  top: 12px;
}
@media (max-width: 640px) {
  .marco-acceso {
    padding: 20px 20px 16px;
    gap: 18px;
  }
  .firma-acceso {
    font-size: 11px;
  }
  .firma-acceso :deep(p:last-child:not(:first-child)) {
    display: none;
  }
}
/* El teclado, el zoom o una pantalla muy baja pueden necesitar desplazamiento para conservar los controles. */
@media (max-height: 620px) {
  .marco-acceso--compacto {
    height: auto;
    min-height: 100svh;
  }
}
</style>
