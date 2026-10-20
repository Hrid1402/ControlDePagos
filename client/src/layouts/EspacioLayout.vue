<script setup lang="ts">
import { ref, computed, inject } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useConfirm } from 'primevue/useconfirm'
import { controlSesionKey } from '@/services/controlSesion'
import Button from 'primevue/button'
import { useSesionStore } from '@/stores/sesion'
import { INICIO_POR_ROL } from '@/router/guard'
const sesion = useSesionStore()
const control = inject(controlSesionKey, null)
const confirmacion = useConfirm()
const router = useRouter()
const menuAbierto = ref(false)
const inicio = computed(() => INICIO_POR_ROL[sesion.rol || 'gerente'])
function cerrar() {
  const salir = () => {
    sesion.cerrar()
    void router.replace({ name: 'login' })
  }
  if (!control?.hayCambios()) {
    salir()
    return
  }
  confirmacion.require({
    header: 'Cambios sin guardar',
    message: 'Si cierras sesión, perderás lo que estás editando.',
    acceptLabel: 'Cerrar sin guardar',
    rejectLabel: 'Seguir editando',
    defaultFocus: 'reject',
    accept: salir,
  })
}
</script>
<template>
  <div class="espacio">
    <a class="saltar" href="#contenido">Ir al contenido</a>
    <div class="firma">
      <RouterLink :to="{ name: inicio }" aria-label="Deconsta, inicio">
        <img
          src="/brand/deconsta/logo/deconsta-wordmark-white.svg"
          alt="Deconsta"
          width="176"
          height="35"
        />
      </RouterLink>
      <p>{{ sesion.rol === 'gerente' ? 'Espacio del gerente' : 'Espacio de la asistente' }}</p>
    </div>
    <main id="contenido" tabindex="-1"><RouterView /></main>
    <div class="barra-trabajo">
      <Button
        class="abrir-menu"
        label="Menú"
        icon="pi pi-bars"
        text
        :aria-expanded="menuAbierto"
        aria-controls="navegacion"
        @click="menuAbierto = !menuAbierto"
      />
      <nav id="navegacion" aria-label="Espacios de trabajo" :class="{ abierta: menuAbierto }">
        <RouterLink :to="{ name: inicio }" @click="menuAbierto = false">Mi espacio</RouterLink>
      </nav>
      <div class="identidad">
        <span class="nombre">{{ sesion.usuario?.nombre }}</span>
        <Button label="Cerrar sesión" icon="pi pi-sign-out" text @click="cerrar" />
      </div>
    </div>
  </div>
</template>
<style scoped>
.espacio {
  min-height: 100svh;
  color: var(--deconsta-ink);
  background: var(--deconsta-paper);
  padding: clamp(24px, 5vw, 72px);
  padding-bottom: 140px;
}
.firma {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 24px;
}
.firma > a {
  background: var(--deconsta-primary);
  padding: 12px 18px;
  border-radius: 8px;
}
.firma img {
  display: block;
  max-width: 100%;
  height: auto;
}
.firma p {
  font-size: 0.875rem;
  color: var(--deconsta-muted);
  margin: 0;
}
main {
  max-width: 1120px;
  margin: clamp(56px, 12vh, 120px) auto 0;
  outline: none;
}
.barra-trabajo {
  position: fixed;
  z-index: 10;
  bottom: 24px;
  left: 24px;
  right: 24px;
  max-width: 1120px;
  margin: auto;
  background: #fff;
  border: 1px solid #bccbc5;
  border-radius: 16px;
  padding: 8px 12px;
  display: flex;
  align-items: center;
  gap: 24px;
  box-shadow: 0 8px 32px #192c2912;
}
nav a {
  color: var(--deconsta-primary);
  text-decoration: none;
  padding: 12px;
  display: inline-block;
  border-radius: 8px;
}
nav a.router-link-active {
  background: #e3eeea;
}
.identidad {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-left: auto;
  min-width: 0;
}
.nombre {
  overflow-wrap: anywhere;
  font-size: 0.875rem;
}
.abrir-menu {
  display: none;
}
a:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 4px;
}
.saltar {
  position: fixed;
  top: -100px;
  background: white;
  padding: 16px;
  z-index: 30;
}
.saltar:focus {
  top: 12px;
}
@media (max-width: 640px) {
  .barra-trabajo {
    bottom: 12px;
    left: 12px;
    right: 12px;
    gap: 8px;
    padding: 8px;
  }
  .abrir-menu {
    display: inline-flex;
  }
  nav {
    display: none;
    position: absolute;
    bottom: calc(100% + 8px);
    left: 0;
    right: 0;
    background: white;
    padding: 8px;
    border: 1px solid #bccbc5;
    border-radius: 12px;
  }
  nav.abierta {
    display: block;
  }
  .identidad {
    gap: 4px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  .nombre {
    max-width: 125px;
  }
}
</style>
