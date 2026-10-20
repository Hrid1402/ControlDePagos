<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import Menu from 'primevue/menu'
import type { MenuItem } from 'primevue/menuitem'
import { SECCIONES, nombreRuta } from '@/config/navegacion'
import type { Rol } from '@/types/api'

const props = defineProps<{ rol: Rol }>()
const route = useRoute()
const router = useRouter()
const mas = ref<InstanceType<typeof Menu>>()

const pestanas = computed(() =>
  SECCIONES[props.rol].map((seccion) => ({
    ...seccion,
    nombre: nombreRuta(props.rol, seccion.clave),
  })),
)
// Una pestaña sigue marcada en sus subpáginas, por ejemplo el detalle de una asistente.
function esActual(pestana: { nombre: string; clave: string }) {
  return (
    pestana.nombre === route.name ||
    (!!pestana.clave && route.path.startsWith(`/${props.rol}/${pestana.clave}/`))
  )
}
const secundarias = computed(() => pestanas.value.filter((p) => !p.principal))
const secundariaActiva = computed(() => secundarias.value.some(esActual))
const opcionesMas = computed<MenuItem[]>(() =>
  secundarias.value.map((p) => ({
    label: p.etiqueta,
    class: esActual(p) ? 'opcion-activa' : undefined,
    command: () => void router.push({ name: p.nombre }),
  })),
)
</script>

<template>
  <nav class="pestanas" aria-label="Secciones">
    <ul>
      <li
        v-for="pestana in pestanas"
        :key="pestana.nombre"
        :class="{ secundaria: !pestana.principal, actual: esActual(pestana) }"
      >
        <RouterLink
          :to="{ name: pestana.nombre }"
          :class="{ activa: esActual(pestana) }"
          active-class=""
          exact-active-class=""
          :aria-current="esActual(pestana) ? 'page' : undefined"
        >
          {{ pestana.etiqueta }}
        </RouterLink>
      </li>
      <li v-if="secundarias.length" class="mas">
        <button
          type="button"
          :class="{ activa: secundariaActiva }"
          aria-haspopup="true"
          aria-controls="secciones-mas"
          @click="mas?.toggle($event)"
        >
          Más<span class="pi pi-angle-down" aria-hidden="true"></span>
        </button>
        <Menu id="secciones-mas" ref="mas" :model="opcionesMas" popup />
      </li>
    </ul>
  </nav>
</template>

<style scoped>
ul {
  display: flex;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
  overflow-x: auto;
  scrollbar-width: none;
}
ul::-webkit-scrollbar {
  display: none;
}
li {
  flex-shrink: 0;
}
a,
button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 46px;
  padding: 0 18px;
  border: 0;
  border-radius: 12px 12px 0 0;
  background: transparent;
  color: var(--deconsta-sobre-mesa);
  font-size: 0.9375rem;
  font-weight: 600;
  text-decoration: none;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background-color 0.18s ease,
    color 0.18s ease;
}
a:hover,
button:hover {
  background: rgb(241 244 241 / 0.1);
  color: var(--deconsta-paper);
}
/* La pestaña actual es papel: se funde con la hoja de abajo. */
a.activa,
button.activa {
  background: var(--deconsta-paper);
  color: var(--deconsta-ink);
}
a:focus-visible,
button:focus-visible {
  outline: 3px solid var(--deconsta-paper);
  outline-offset: -5px;
}
a.activa:focus-visible,
button.activa:focus-visible {
  outline-color: var(--deconsta-primary);
}
.pi {
  font-size: 0.75rem;
}
/* En escritorio las secundarias viven en «Más», salvo la que está abierta. */
@media (min-width: 768px) {
  .secundaria:not(.actual) {
    display: none;
  }
}
@media (max-width: 767px) {
  /* El desvanecido del borde derecho indica que hay más pestañas al desplazar. */
  ul {
    mask-image: linear-gradient(to right, #000 calc(100% - 32px), transparent);
    padding-right: 24px;
  }
  .mas {
    display: none;
  }
  a {
    padding: 0 14px;
    min-height: 44px;
  }
}
</style>

<style>
.p-menu .opcion-activa .p-menu-item-content {
  background: var(--deconsta-realce);
  font-weight: 600;
}
</style>
