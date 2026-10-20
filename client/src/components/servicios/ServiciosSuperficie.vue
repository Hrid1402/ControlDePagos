<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import Button from 'primevue/button'
import { tintaSobre } from '@/components/categorias/modelo'
import {
  lugarEn,
  nombreServicio,
  type CategoriaServicio,
  type FiltroEstado,
  type Servicio,
} from './modelo'

// H10 CA08 a CA10: servicios con búsqueda y filtro por categoría. Quien la usa trae los datos y
// decide qué pasa al buscar, filtrar o elegir una acción.
const props = withDefaults(
  defineProps<{
    servicios?: Servicio[]
    total?: number
    categorias?: CategoriaServicio[]
    busqueda?: string
    categoria?: string
    estado?: FiltroEstado
    estadoPantalla?: 'lista' | 'cargando' | 'error'
    hayMas?: boolean
    cargandoMas?: boolean
    /** Solo el gerente da de baja y reactiva. */
    puedeDarDeBaja?: boolean
    ocupado?: string | null
  }>(),
  {
    servicios: () => [],
    total: 0,
    categorias: () => [],
    busqueda: '',
    categoria: '',
    estado: 'activo',
    estadoPantalla: 'lista',
    hayMas: false,
    cargandoMas: false,
    puedeDarDeBaja: false,
    ocupado: null,
  },
)
const emit = defineEmits<{
  buscar: [texto: string]
  filtrarCategoria: [id: string]
  filtrarEstado: [estado: FiltroEstado]
  crear: []
  editar: [id: string]
  baja: [id: string]
  reactivar: [id: string]
  reintentar: []
  mas: []
}>()

const ESTADOS: { valor: FiltroEstado; etiqueta: string }[] = [
  { valor: 'activo', etiqueta: 'Activos' },
  { valor: 'baja', etiqueta: 'De baja' },
  { valor: 'todos', etiqueta: 'Todos' },
]

// La búsqueda espera a que se deje de escribir para no pedir una lista por cada tecla.
const texto = ref(props.busqueda)
let espera: ReturnType<typeof setTimeout> | undefined
watch(
  () => props.busqueda,
  (nuevo) => (texto.value = nuevo),
)
function escribir(valor: string) {
  texto.value = valor
  clearTimeout(espera)
  espera = setTimeout(() => emit('buscar', valor.trim()), 300)
}
onBeforeUnmount(() => clearTimeout(espera))

const hayFiltros = () => !!props.busqueda || !!props.categoria || props.estado !== 'activo'
</script>

<template>
  <section class="servicios" aria-labelledby="servicios-titulo">
    <header class="encabezado">
      <div>
        <h1 id="servicios-titulo">Servicios</h1>
        <p>Lo que pagas cada mes, con su empresa, su código y dónde se paga.</p>
      </div>
      <Button label="Nuevo servicio" icon="pi pi-plus" @click="emit('crear')" />
    </header>

    <div class="herramientas">
      <label class="buscador">
        <i class="pi pi-search" aria-hidden="true"></i>
        <span class="lector">Buscar servicios</span>
        <input
          type="search"
          :value="texto"
          placeholder="Busca por alias, empresa, código o titular"
          @input="escribir(($event.target as HTMLInputElement).value)"
        />
      </label>
      <div class="estados" role="group" aria-label="Mostrar servicios">
        <button
          v-for="e in ESTADOS"
          :key="e.valor"
          type="button"
          :aria-pressed="estado === e.valor"
          @click="emit('filtrarEstado', e.valor)"
        >
          {{ e.etiqueta }}
        </button>
      </div>
    </div>

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
      <p class="lector" role="status">Cargando servicios…</p>
      <div v-for="n in 4" :key="n" class="marcador"></div>
    </div>

    <div v-else-if="estadoPantalla === 'error'" class="fallo" role="alert">
      <h2>No pudimos cargar tus servicios.</h2>
      <p>Revisa tu conexión e inténtalo otra vez. Tu búsqueda se conserva.</p>
      <Button label="Reintentar" icon="pi pi-refresh" @click="emit('reintentar')" />
    </div>

    <section v-else-if="!servicios.length" class="vacio" aria-live="polite">
      <template v-if="hayFiltros()">
        <h2>Ningún servicio coincide</h2>
        <p>Prueba con otra búsqueda, otra categoría o muestra todos los estados.</p>
      </template>
      <template v-else>
        <h2>Todavía no registras servicios</h2>
        <p>Registra cada servicio una sola vez: sus deudas de cada mes se crean a partir de él.</p>
        <Button label="Registrar el primero" icon="pi pi-plus" outlined @click="emit('crear')" />
      </template>
    </section>

    <template v-else>
      <p class="conteo" role="status">
        {{ total === 1 ? '1 servicio' : `${total} servicios` }}
      </p>
      <ul class="lista">
        <li
          v-for="s in servicios"
          :key="s.id"
          class="servicio"
          :class="{ baja: s.estado === 'baja' }"
        >
          <span
            class="icono"
            aria-hidden="true"
            :style="{ background: s.categoria.color, color: tintaSobre(s.categoria.color) }"
          >
            <i class="pi" :class="s.categoria.icono"></i>
          </span>
          <div class="cuerpo">
            <p class="nombre">
              {{ nombreServicio(s) }}
              <span v-if="s.estado === 'baja'" class="etiqueta-baja">De baja</span>
            </p>
            <p class="dato">
              <span>{{ s.alias ? s.empresa : s.categoria.nombre }}</span>
              <span class="codigo" :aria-label="`Código ${s.codigo_suministro}`">{{
                s.codigo_suministro
              }}</span>
              <span v-if="s.titular">{{ s.titular }}</span>
            </p>
            <p v-if="lugarEn(s.lugar_pago)" class="lugar">
              <i class="pi pi-map-marker" aria-hidden="true"></i>
              Se paga en {{ lugarEn(s.lugar_pago) }}
            </p>
          </div>
          <div class="acciones">
            <button
              v-if="s.estado === 'activo'"
              type="button"
              :aria-label="`Editar ${nombreServicio(s)}`"
              @click="emit('editar', s.id)"
            >
              Editar
            </button>
            <template v-if="puedeDarDeBaja">
              <button
                v-if="s.estado === 'activo'"
                type="button"
                class="peligro"
                :disabled="ocupado === s.id"
                :aria-label="`Dar de baja ${nombreServicio(s)}`"
                @click="emit('baja', s.id)"
              >
                Dar de baja
              </button>
              <button
                v-else
                type="button"
                :disabled="ocupado === s.id"
                :aria-label="`Reactivar ${nombreServicio(s)}`"
                @click="emit('reactivar', s.id)"
              >
                Reactivar
              </button>
            </template>
          </div>
        </li>
      </ul>
      <div v-if="hayMas" class="mas">
        <Button label="Mostrar más" outlined :loading="cargandoMas" @click="emit('mas')" />
        <span>Ves {{ servicios.length }} de {{ total }}</span>
      </div>
    </template>
  </section>
</template>

<style scoped>
.servicios {
  max-width: 1040px;
}
.encabezado {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px 32px;
  margin-bottom: clamp(24px, 4vw, 32px);
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
.herramientas {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}
.buscador {
  position: relative;
  flex: 1 1 320px;
}
.buscador .pi {
  position: absolute;
  top: 50%;
  left: 14px;
  color: var(--deconsta-muted);
  transform: translateY(-50%);
}
.buscador input {
  width: 100%;
  min-height: 46px;
  padding: 0 14px 0 40px;
  border: 1px solid var(--deconsta-linea);
  border-radius: var(--radio-control);
  background: #fff;
  color: var(--deconsta-ink);
  font: inherit;
}
.buscador input:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 1px;
}
.estados {
  display: flex;
  gap: 2px;
  padding: 3px;
  border-radius: var(--radio-control);
  background: var(--deconsta-realce);
}
.estados button {
  min-height: 40px;
  padding: 0 14px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--deconsta-ink);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.estados button[aria-pressed='true'] {
  background: var(--deconsta-primary);
  color: var(--deconsta-paper);
}
/* Las categorías se desplazan de lado en celular en vez de ocupar varias filas. */
.categorias {
  display: flex;
  gap: 8px;
  margin: 14px 0 24px;
  padding-bottom: 4px;
  overflow-x: auto;
  scrollbar-width: thin;
}
.chip {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 8px;
  min-height: 36px;
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
  width: 10px;
  height: 10px;
  border-radius: 50%;
  box-shadow: 0 0 0 1px rgb(255 255 255 / 0.6);
}
button:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 2px;
}
.conteo {
  margin: 0 0 8px;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.lista {
  margin: 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid var(--deconsta-ink);
}
.servicio {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) auto;
  align-items: start;
  gap: 14px 16px;
  padding: 16px 4px;
  border-bottom: 1px solid var(--deconsta-linea);
}
.icono {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 4px 15px 4px 4px;
}
.servicio.baja .icono {
  filter: grayscale(1);
  opacity: 0.55;
}
.cuerpo p {
  margin: 0;
}
.nombre {
  font-weight: 700;
  overflow-wrap: anywhere;
}
.servicio.baja .nombre {
  color: var(--deconsta-muted);
}
.etiqueta-baja {
  margin-left: 8px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--deconsta-realce);
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
  font-weight: 600;
}
.dato {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 14px;
  margin-top: 4px !important;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.codigo {
  color: var(--deconsta-ink);
  font-family: ui-monospace, 'SFMono-Regular', Menlo, monospace;
  letter-spacing: 0.02em;
}
.lugar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px !important;
  font-size: var(--texto-sm);
}
.lugar .pi {
  color: var(--deconsta-primary);
  font-size: 0.8rem;
}
.acciones {
  display: flex;
  gap: 4px;
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
.acciones button:hover:not(:disabled) {
  text-decoration: underline;
  text-underline-offset: 4px;
}
.acciones button:disabled {
  opacity: 0.5;
  cursor: wait;
}
.mas {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  padding-top: 16px;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.vacio {
  max-width: 52ch;
  padding: clamp(20px, 4vw, 40px) 0;
}
.vacio h2 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-lg);
  font-weight: 500;
}
.vacio p {
  margin: 8px 0 20px;
  color: var(--deconsta-muted);
  line-height: 1.6;
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
  height: 76px;
  margin-bottom: 8px;
  border-radius: var(--radio-control);
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
@media (max-width: 600px) {
  .encabezado :deep(.p-button) {
    width: 100%;
  }
  .estados {
    width: 100%;
  }
  .estados button {
    flex: 1 1 0;
  }
  .servicio {
    grid-template-columns: 40px minmax(0, 1fr);
  }
  .icono {
    width: 40px;
    height: 40px;
  }
  .acciones {
    grid-column: 2;
    margin: -6px 0 0 -8px;
  }
}
</style>
