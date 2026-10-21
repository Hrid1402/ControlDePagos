<script setup lang="ts">
import { computed } from 'vue'
import Button from 'primevue/button'
import { importe, MONEDAS } from '@/components/deudas/modelo'
import type { CategoriaDeuda } from '@/components/deudas/listado'
import TarjetaBandeja from './TarjetaBandeja.vue'
import {
  PESTANAS,
  totalesSeleccion,
  type Contadores,
  type ItemBandeja,
  type Pestana,
} from './modelo'

// H15: la pantalla de inicio de la asistente (CA01). Lo urgente primero, con pestañas y
// contadores (CA03), filtro por categoría (CA11) y selección múltiple para la ruta (CA12). Quien
// la usa trae los datos y ejecuta cada acción (TASK-50).
const props = withDefaults(
  defineProps<{
    items?: ItemBandeja[]
    contadores?: Contadores
    pestana: Pestana
    categoria?: string
    categorias?: CategoriaDeuda[]
    estadoPantalla?: 'lista' | 'cargando' | 'error'
    hoy: string
    seleccion?: string[]
    usuarioId?: string
    ocupado?: string | null
    nombre?: string
  }>(),
  {
    items: () => [],
    contadores: () => ({ por_pagar: 0, por_validar: 0, rechazadas: 0 }),
    categoria: '',
    categorias: () => [],
    estadoPantalla: 'lista',
    seleccion: () => [],
    usuarioId: '',
    ocupado: null,
    nombre: '',
  },
)
const emit = defineEmits<{
  cambiarPestana: [pestana: Pestana]
  filtrarCategoria: [id: string]
  seleccionar: [ids: string[]]
  abrir: [id: string]
  ventanilla: [id: string]
  adjuntar: [id: string]
  fijar: [id: string, valor: boolean]
  posponer: [id: string]
  agregarRuta: []
  reintentar: []
}>()

const seleccionadas = computed(() => props.items.filter((i) => props.seleccion.includes(i.id)))
const totales = computed(() =>
  MONEDAS.flatMap((m) => {
    const valor = totalesSeleccion(seleccionadas.value)[m.valor]
    return valor ? [importe(valor, m.valor)] : []
  }),
)
const urgentes = computed(() => props.items.filter((i) => i.nivel <= 3).length)
const pestanaActual = computed(() => PESTANAS.find((p) => p.valor === props.pestana)!)
const todoAlDia = computed(
  () =>
    props.contadores.por_pagar + props.contadores.por_validar + props.contadores.rechazadas === 0,
)

function alternar(id: string, valor: boolean) {
  emit('seleccionar', valor ? [...props.seleccion, id] : props.seleccion.filter((s) => s !== id))
}
</script>

<template>
  <section class="bandeja" aria-labelledby="bandeja-titulo">
    <header class="encabezado">
      <h1 id="bandeja-titulo">{{ nombre ? `Hola, ${nombre.split(' ')[0]}` : 'Bandeja' }}</h1>
      <p v-if="estadoPantalla === 'lista' && pestana === 'por_pagar' && urgentes">
        Tienes
        <strong>{{ urgentes === 1 ? '1 deuda urgente' : `${urgentes} deudas urgentes` }}</strong>
        para hoy. Empieza por arriba.
      </p>
      <p v-else>
        Lo más urgente primero. Fija lo que quieras atender antes o pospónlo hasta mañana.
      </p>
    </header>

    <nav class="pestanas" aria-label="Pestañas de la bandeja">
      <button
        v-for="p in PESTANAS"
        :key="p.valor"
        type="button"
        :aria-current="pestana === p.valor ? 'page' : undefined"
        :class="{
          activa: pestana === p.valor,
          alerta: p.valor === 'rechazadas' && contadores.rechazadas > 0,
        }"
        @click="emit('cambiarPestana', p.valor)"
      >
        {{ p.etiqueta }}
        <span class="contador">{{ contadores[p.valor] }}</span>
      </button>
    </nav>

    <div
      v-if="categorias.length"
      class="categorias"
      role="group"
      aria-label="Filtrar por categoría"
    >
      <button
        type="button"
        class="chip"
        :aria-pressed="!categoria"
        @click="emit('filtrarCategoria', '')"
      >
        Todas
      </button>
      <button
        v-for="c in categorias"
        :key="c.id"
        type="button"
        class="chip"
        :aria-pressed="categoria === c.id"
        @click="emit('filtrarCategoria', c.id)"
      >
        <span class="punto" :style="{ background: c.color }" aria-hidden="true"></span>
        {{ c.nombre }}
      </button>
    </div>

    <div v-if="estadoPantalla === 'cargando'" aria-busy="true">
      <p class="lector" role="status">Cargando la bandeja…</p>
      <div v-for="n in 4" :key="n" class="marcador"></div>
    </div>

    <div v-else-if="estadoPantalla === 'error'" class="fallo" role="alert">
      <h2>No pudimos cargar la bandeja.</h2>
      <p>Revisa tu conexión e inténtalo otra vez.</p>
      <Button label="Reintentar" icon="pi pi-refresh" @click="emit('reintentar')" />
    </div>

    <section v-else-if="!items.length" class="vacio" aria-live="polite">
      <span class="vacio-icono" aria-hidden="true"><i class="pi pi-check"></i></span>
      <template v-if="todoAlDia && !categoria">
        <h2>Todo al día</h2>
        <p>No hay deudas por pagar ni comprobantes pendientes. Buen trabajo.</p>
      </template>
      <template v-else>
        <h2>{{ pestanaActual.vacia }}</h2>
        <p v-if="categoria">Prueba con «Todas» las categorías.</p>
      </template>
    </section>

    <ul v-else class="lista">
      <li v-for="item in items" :key="item.id">
        <TarjetaBandeja
          :item="item"
          :pestana="pestana"
          :hoy="hoy"
          :usuario-id="usuarioId"
          :seleccionada="seleccion.includes(item.id)"
          :ocupada="ocupado === item.id"
          @seleccionar="alternar(item.id, $event)"
          @abrir="emit('abrir', item.id)"
          @ventanilla="emit('ventanilla', item.id)"
          @adjuntar="emit('adjuntar', item.id)"
          @fijar="emit('fijar', item.id, $event)"
          @posponer="emit('posponer', item.id)"
        />
      </li>
    </ul>

    <div v-if="seleccion.length" class="seleccion" role="region" aria-label="Deudas seleccionadas">
      <p>
        <strong>{{ seleccion.length === 1 ? '1 deuda' : `${seleccion.length} deudas` }}</strong>
        · llevar {{ totales.join(' + ') }}
      </p>
      <div class="seleccion-acciones">
        <Button label="Quitar" text size="small" @click="emit('seleccionar', [])" />
        <Button label="Agregar a la ruta" icon="pi pi-directions" @click="emit('agregarRuta')" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.bandeja {
  max-width: 880px;
}
.encabezado {
  margin-bottom: 22px;
}
h1 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-xl);
  font-weight: 500;
  letter-spacing: -0.02em;
}
.encabezado p {
  margin: 8px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-md);
}
.encabezado strong {
  color: var(--deconsta-error);
}
.pestanas {
  display: flex;
  gap: 4px;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--deconsta-linea);
  overflow-x: auto;
}
.pestanas button {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 8px;
  min-height: 46px;
  padding: 0 14px;
  border: 0;
  border-bottom: 3px solid transparent;
  background: none;
  color: var(--deconsta-muted);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}
.pestanas button.activa {
  border-bottom-color: var(--deconsta-primary);
  color: var(--deconsta-ink);
}
.contador {
  min-width: 24px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--deconsta-realce);
  color: var(--deconsta-ink);
  font-size: var(--texto-xs);
  text-align: center;
}
.activa .contador {
  background: var(--deconsta-primary);
  color: var(--deconsta-paper);
}
.alerta .contador {
  background: var(--deconsta-error);
  color: #fff;
}
.categorias {
  display: flex;
  gap: 8px;
  margin-bottom: 18px;
  padding-bottom: 4px;
  overflow-x: auto;
}
.chip {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid var(--deconsta-linea);
  border-radius: 999px;
  background: var(--deconsta-paper-claro);
  color: var(--deconsta-ink);
  font: inherit;
  font-size: var(--texto-sm);
  cursor: pointer;
}
.chip[aria-pressed='true'] {
  border-color: var(--deconsta-ink);
  background: var(--deconsta-ink);
  color: var(--deconsta-paper);
}
.punto {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
button:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 2px;
}
.lista {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.seleccion {
  position: sticky;
  bottom: 16px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px 16px;
  margin-top: 18px;
  padding: 12px 16px 12px 20px;
  border-radius: 6px 18px 6px 6px;
  background: var(--deconsta-ink);
  box-shadow: 0 10px 30px rgb(25 44 41 / 0.25);
  color: var(--deconsta-paper);
}
.seleccion p {
  margin: 0;
  font-variant-numeric: tabular-nums;
}
.seleccion-acciones {
  display: flex;
  gap: 6px;
}
.seleccion :deep(.p-button-text) {
  color: var(--deconsta-sobre-mesa);
}
.vacio {
  padding: clamp(32px, 6vw, 64px) 0;
  text-align: center;
}
.vacio-icono {
  display: inline-grid;
  place-items: center;
  width: 64px;
  height: 64px;
  margin-bottom: 14px;
  border-radius: 50%;
  background: var(--deconsta-realce);
  color: var(--deconsta-primary);
  font-size: 1.6rem;
}
.vacio h2 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-lg);
  font-weight: 500;
}
.vacio p {
  margin: 8px 0 0;
  color: var(--deconsta-muted);
}
.fallo {
  max-width: 52ch;
  padding: 24px 28px;
  border-left: 3px solid var(--deconsta-error);
  background: var(--deconsta-error-fondo);
}
.fallo h2 {
  margin: 0;
  font-size: var(--texto-lg);
}
.fallo p {
  margin: 8px 0 20px;
}
.marcador {
  height: 132px;
  margin-bottom: 12px;
  border-radius: 6px 18px 6px 6px;
  background: linear-gradient(90deg, #e6ece9 0%, #f4f7f5 50%, #e6ece9 100%) 0 0 / 200% 100%;
  animation: brillo 1.4s ease-in-out infinite;
}
@keyframes brillo {
  to {
    background-position: -200% 0;
  }
}
.lector {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
