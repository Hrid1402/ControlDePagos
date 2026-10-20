<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import { useToast } from 'primevue/usetoast'
import DialogoCategoria from '@/components/categorias/DialogoCategoria.vue'
import DialogoEliminarCategoria from '@/components/categorias/DialogoEliminarCategoria.vue'
import { listarCategorias } from '@/api/categorias'
import { etiquetaTipo, plural, tintaSobre, type Categoria } from '@/components/categorias/modelo'
import { useSesionStore } from '@/stores/sesion'

// H09 (TASK-29): categorías precargadas y propias, con sus servicios y deudas (CA06). Gerente y
// asistente crean; solo el gerente edita y elimina (CA04), y nunca una precargada (CA01).
const sesion = useSesionStore()
const toast = useToast()

const categorias = ref<Categoria[]>([])
const estado = ref<'cargando' | 'lista' | 'error'>('cargando')
const editando = ref<Categoria | null>(null)
const creando = ref(false)
const eliminando = ref<Categoria | null>(null)

const esGerente = computed(() => sesion.usuario?.rol === 'gerente')
const grupos = computed(() =>
  [
    {
      clave: 'precargadas',
      titulo: 'Precargadas',
      nota: 'Vienen con tu cuenta: puedes editarlas, pero no eliminarlas.',
      items: categorias.value.filter((c) => c.precargada),
    },
    {
      clave: 'propias',
      titulo: 'Tus categorías',
      nota: null,
      items: categorias.value.filter((c) => !c.precargada),
    },
  ].filter((g) => g.items.length || g.clave === 'propias'),
)

async function cargar() {
  if (!categorias.value.length) estado.value = 'cargando'
  try {
    categorias.value = await listarCategorias()
    estado.value = 'lista'
  } catch {
    if (!categorias.value.length) estado.value = 'error'
  }
}
onMounted(cargar)

async function alGuardar() {
  creando.value = false
  editando.value = null
  await cargar()
}

async function alEliminar(movidos: number) {
  const nombre = eliminando.value?.nombre ?? 'La categoría'
  eliminando.value = null
  toast.add({
    severity: 'success',
    summary: 'Categoría eliminada',
    detail: movidos
      ? `${nombre} se eliminó y ${plural(movidos, 'servicio pasó', 'servicios pasaron')} a otra categoría.`
      : `${nombre} se eliminó.`,
    life: 5000,
  })
  await cargar()
}
</script>

<template>
  <div class="categorias">
    <header class="encabezado">
      <div>
        <h1>Categorías</h1>
        <p>Agrupa tus servicios por tipo de gasto. El tipo decide qué pide cada deuda.</p>
      </div>
      <Button label="Nueva categoría" icon="pi pi-plus" @click="creando = true" />
    </header>

    <div v-if="estado === 'cargando'" aria-busy="true" class="rejilla">
      <p class="lector" role="status">Cargando categorías…</p>
      <div v-for="n in 6" :key="n" class="marcador"></div>
    </div>

    <div v-else-if="estado === 'error'" class="fallo" role="alert">
      <h2>No pudimos cargar tus categorías.</h2>
      <p>Revisa tu conexión e inténtalo otra vez.</p>
      <Button label="Reintentar" icon="pi pi-refresh" @click="cargar" />
    </div>

    <template v-else>
      <section
        v-for="grupo in grupos"
        :key="grupo.clave"
        class="grupo"
        :aria-labelledby="`grupo-${grupo.clave}`"
      >
        <header class="grupo-cabecera">
          <h2 :id="`grupo-${grupo.clave}`">{{ grupo.titulo }}</h2>
          <p v-if="grupo.nota">{{ grupo.nota }}</p>
        </header>
        <p v-if="!grupo.items.length" class="vacio">
          Todavía no creaste categorías propias. Crea una para agrupar lo que no encaja en las
          precargadas.
        </p>
        <ul v-else class="rejilla">
          <li v-for="c in grupo.items" :key="c.id" class="ficha">
            <div class="ficha-cabecera">
              <span
                class="icono"
                aria-hidden="true"
                :style="{ background: c.color, color: tintaSobre(c.color) }"
              >
                <i class="pi" :class="c.icono"></i>
              </span>
              <div class="titulo">
                <h3>{{ c.nombre }}</h3>
                <p>{{ etiquetaTipo(c.tipo) }}</p>
              </div>
            </div>
            <dl class="cifras">
              <div>
                <dt>Servicios</dt>
                <dd>{{ c.cantidad_servicios }}</dd>
              </div>
              <div>
                <dt>Deudas</dt>
                <dd>{{ c.cantidad_deudas }}</dd>
              </div>
            </dl>
            <div v-if="esGerente" class="acciones">
              <button type="button" :aria-label="`Editar ${c.nombre}`" @click="editando = c">
                Editar
              </button>
              <button
                v-if="!c.precargada"
                type="button"
                class="peligro"
                :aria-label="`Eliminar ${c.nombre}`"
                @click="eliminando = c"
              >
                Eliminar
              </button>
            </div>
          </li>
        </ul>
      </section>
    </template>

    <DialogoCategoria
      v-if="creando || editando"
      :categoria="editando"
      @guardada="alGuardar"
      @cerrar="((creando = false), (editando = null))"
    />
    <DialogoEliminarCategoria
      v-if="eliminando"
      :categoria="eliminando"
      :todas="categorias"
      @eliminada="alEliminar"
      @cerrar="eliminando = null"
    />
  </div>
</template>

<style scoped>
.categorias {
  max-width: 1120px;
}
.encabezado {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px 32px;
  margin-bottom: clamp(24px, 4vw, 36px);
}
h1 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-xl);
  font-weight: 500;
  letter-spacing: -0.02em;
  line-height: 1.15;
}
.encabezado p {
  margin: 10px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-md);
}
.encabezado :deep(.p-button) {
  min-height: 44px;
}
.grupo + .grupo {
  margin-top: clamp(32px, 5vw, 48px);
}
.grupo-cabecera {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 16px;
  margin-bottom: 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--deconsta-ink);
}
.grupo-cabecera h2 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-lg);
  font-weight: 500;
}
.grupo-cabecera p {
  margin: 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.rejilla {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 240px), 1fr));
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}
/* Cada categoría es una ficha de la marca: papel claro y la esquina asimétrica. */
.ficha {
  display: grid;
  grid-template-rows: auto 1fr auto;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--deconsta-linea);
  border-radius: 5px 22px 5px 5px;
  background: var(--deconsta-paper-claro);
}
.ficha-cabecera {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.icono {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  border-radius: 4px 15px 4px 4px;
  font-size: 1.125rem;
}
.titulo {
  min-width: 0;
}
h3 {
  margin: 0;
  font-size: var(--texto-md);
  font-weight: 700;
  overflow-wrap: anywhere;
}
.titulo p {
  margin: 2px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.cifras {
  display: flex;
  gap: 24px;
  margin: 0;
}
.cifras div {
  display: flex;
  flex-direction: column-reverse;
}
dt {
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
}
dd {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: 1.375rem;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.acciones {
  display: flex;
  gap: 4px;
  margin: 0 -8px -6px;
  padding-top: 8px;
  border-top: 1px solid var(--deconsta-linea);
}
.acciones button {
  min-height: 36px;
  padding: 0 8px;
  border: 0;
  border-radius: 2px;
  background: transparent;
  color: var(--deconsta-primary);
  font: inherit;
  font-size: var(--texto-sm);
  font-weight: 600;
  cursor: pointer;
}
.acciones button.peligro {
  color: var(--deconsta-error);
}
.acciones button:hover {
  text-decoration: underline;
  text-underline-offset: 4px;
}
.acciones button:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 2px;
}
.vacio {
  max-width: 60ch;
  margin: 0;
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
  height: 148px;
  border-radius: 5px 22px 5px 5px;
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
/* En celular la ficha se aplana: cifras y acciones comparten fila para ver más categorías. */
@media (max-width: 520px) {
  .encabezado :deep(.p-button) {
    width: 100%;
  }
  .ficha {
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-rows: auto auto;
    gap: 10px 12px;
    padding: 14px;
  }
  .ficha-cabecera {
    grid-column: 1 / -1;
  }
  .cifras {
    gap: 18px;
  }
  dd {
    font-size: 1.125rem;
  }
  .acciones {
    align-self: end;
    margin: 0 -6px -4px 0;
    padding-top: 0;
    border-top: 0;
  }
}
</style>
