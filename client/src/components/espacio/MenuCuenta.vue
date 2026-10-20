<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import Menu from 'primevue/menu'
import type { MenuItem } from 'primevue/menuitem'
import { CUENTA, nombreRuta } from '@/config/navegacion'
import type { UsuarioSesion } from '@/types/api'

const props = defineProps<{ usuario: UsuarioSesion }>()
const emit = defineEmits<{ cerrar: [] }>()
const router = useRouter()
const menu = ref<InstanceType<typeof Menu>>()

const iniciales = computed(() =>
  props.usuario.nombre
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((parte) => parte[0]!.toLocaleUpperCase('es'))
    .join(''),
)
const rolVisible = computed(() => (props.usuario.rol === 'gerente' ? 'Gerente' : 'Asistente'))
const opciones = computed<MenuItem[]>(() => [
  {
    label: 'Mi cuenta',
    icon: 'pi pi-user',
    command: () => void router.push({ name: nombreRuta(props.usuario.rol, CUENTA) }),
  },
  { separator: true },
  { label: 'Cerrar sesión', icon: 'pi pi-sign-out', command: () => emit('cerrar') },
])
</script>

<template>
  <div class="menu-cuenta">
    <button
      type="button"
      class="disparador"
      :aria-label="`Tu cuenta: ${usuario.nombre}, ${rolVisible}`"
      aria-haspopup="true"
      aria-controls="menu-cuenta"
      @click="menu?.toggle($event)"
    >
      <span class="monograma" aria-hidden="true">{{ iniciales }}</span>
      <span class="quien">
        <span class="nombre">{{ usuario.nombre }}</span>
        <span class="rol">{{ rolVisible }}</span>
      </span>
      <span class="pi pi-angle-down" aria-hidden="true"></span>
    </button>
    <Menu id="menu-cuenta" ref="menu" :model="opciones" popup />
  </div>
</template>

<style scoped>
.disparador {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 48px;
  max-width: min(320px, 60vw);
  padding: 4px 10px 4px 4px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--deconsta-paper);
  cursor: pointer;
  text-align: left;
}
.disparador:hover {
  background: rgb(241 244 241 / 0.1);
}
.disparador:focus-visible {
  outline: 3px solid var(--deconsta-paper);
  outline-offset: 2px;
}
/* Mismo corte asimétrico que la hoja: la identidad se lee como parte de la marca. */
.monograma {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 4px 14px 4px 4px;
  background: var(--deconsta-paper);
  color: var(--deconsta-primary);
  font-family: Literata, Georgia, serif;
  font-size: 1rem;
  font-weight: 600;
}
.quien {
  display: grid;
  min-width: 0;
  line-height: 1.25;
}
.nombre {
  overflow: hidden;
  font-size: var(--texto-sm);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rol {
  color: var(--deconsta-sobre-mesa);
  font-size: var(--texto-xs);
}
.pi {
  font-size: 0.75rem;
}
@media (max-width: 640px) {
  .quien {
    display: none;
  }
  .disparador {
    gap: 6px;
    padding-right: 8px;
  }
}
</style>
