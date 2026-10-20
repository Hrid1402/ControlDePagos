<script setup lang="ts">
import { computed, inject } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useConfirm } from 'primevue/useconfirm'
import { controlSesionKey } from '@/services/controlSesion'
import { useSesionStore } from '@/stores/sesion'
import { INICIO_POR_ROL } from '@/router/guard'
import PestanasEspacio from '@/components/espacio/PestanasEspacio.vue'
import MenuCuenta from '@/components/espacio/MenuCuenta.vue'

// El espacio es la hoja del acceso llevada al trabajo diario: la mesa verde enmarca, las
// pestañas de índice salen del borde de la hoja y la cuenta queda siempre a mano (RG08).
const sesion = useSesionStore()
const control = inject(controlSesionKey, null)
const confirmacion = useConfirm()
const router = useRouter()
const rol = computed(() => sesion.rol || 'gerente')
const inicio = computed(() => INICIO_POR_ROL[rol.value])
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
    <header class="borde-mesa">
      <RouterLink :to="{ name: inicio }" class="marca" aria-label="Deconsta, inicio">
        <img
          src="/brand/deconsta/logo/deconsta-wordmark-white.svg"
          alt="Deconsta"
          width="132"
          height="26"
        />
      </RouterLink>
      <MenuCuenta v-if="sesion.usuario" :usuario="sesion.usuario" @cerrar="cerrar" />
    </header>
    <PestanasEspacio :rol="rol" />
    <main id="contenido" class="hoja" tabindex="-1"><RouterView /></main>
  </div>
</template>

<style scoped>
.espacio {
  display: flex;
  flex-direction: column;
  min-height: 100svh;
  padding: 0 var(--margen-mesa) var(--margen-mesa);
  background: var(--deconsta-primary);
  color: var(--deconsta-paper);
}
.borde-mesa {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 72px;
}
.marca {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  border-radius: 4px;
}
.marca img {
  display: block;
  width: clamp(112px, 10vw, 132px);
  height: auto;
}
.marca:focus-visible {
  outline: 3px solid var(--deconsta-paper);
  outline-offset: 6px;
}
.hoja {
  flex: 1;
  min-width: 0;
  padding: clamp(24px, 4vw, 56px);
  border-radius: var(--radio-hoja);
  background: var(--deconsta-paper);
  color: var(--deconsta-ink);
  outline: none;
}
/* Si la primera pestaña está abierta, la hoja continúa recta bajo ella. */
.espacio:has(.pestanas li:first-child a.activa) .hoja {
  border-top-left-radius: 0;
}
.saltar {
  position: fixed;
  top: -100px;
  left: 16px;
  z-index: 30;
  padding: 16px;
  background: var(--deconsta-paper);
  color: var(--deconsta-primary);
}
.saltar:focus {
  top: 12px;
}
@media (max-width: 767px) {
  .borde-mesa {
    min-height: 60px;
  }
  .hoja {
    padding: 24px 20px 32px;
    border-radius: 5px 28px 5px 5px;
  }
}
</style>
