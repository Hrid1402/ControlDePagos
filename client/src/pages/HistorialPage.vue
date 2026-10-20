<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import RegistroHistorial from '@/components/historial/RegistroHistorial.vue'
import {
  OPCIONES_ACCION,
  dia,
  tituloDia,
  type FiltrosHistorial,
  type RegistroHistorial as Registro,
} from '@/components/historial/modelo'
import { TAMANO_PAGINA, exportarHistorial, listarHistorial } from '@/api/historial'
import { listarAsistentes } from '@/api/asistentes'
import { useSesionStore } from '@/stores/sesion'
import { nombreDe, type AsistenteFila } from '@/types/asistentes'
import type { ErrorApi } from '@/types/api'

// H34: quién hizo qué y cuándo (TASK-19). Los filtros viven en la URL: se pueden compartir y
// sobreviven a recargar la página. El listado y el Excel usan los mismos (CA03 y CA05).
const route = useRoute()
const router = useRouter()
const sesion = useSesionStore()

const registros = ref<Registro[]>([])
const total = ref(0)
const pagina = ref(1)
const estado = ref<'cargando' | 'lista' | 'error'>('cargando')
const cargandoMas = ref(false)
const errorMas = ref('')
const exportando = ref(false)
const errorExportacion = ref('')
const personas = ref<{ valor: string; etiqueta: string }[]>([])
const cuentas = ref<AsistenteFila[]>([])
let solicitud: AbortController | null = null

const texto = (valor: unknown) => (typeof valor === 'string' ? valor : '')
const filtros = computed<FiltrosHistorial>(() => ({
  usuario: texto(route.query.usuario),
  accion: texto(route.query.accion),
  desde: texto(route.query.desde),
  hasta: texto(route.query.hasta),
}))
const hayFiltros = computed(() => Object.values(filtros.value).some(Boolean))
const fechasInvalidas = computed(
  () => !!filtros.value.desde && !!filtros.value.hasta && filtros.value.desde > filtros.value.hasta,
)
const hoy = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Lima' })
const nombres = computed(() => Object.fromEntries(cuentas.value.map((c) => [c.id, nombreDe(c)])))
const quedan = computed(() => total.value - registros.value.length)

/** Registros agrupados por día de Lima, en el orden en que llegan (los más recientes primero). */
const dias = computed(() => {
  const grupos: { dia: string; registros: Registro[] }[] = []
  for (const registro of registros.value) {
    const clave = dia(registro.creado_en)
    const ultimo = grupos[grupos.length - 1]
    if (ultimo?.dia === clave) ultimo.registros.push(registro)
    else grupos.push({ dia: clave, registros: [registro] })
  }
  return grupos
})

// Cada cambio parte de la URL que dejó el anterior: dos filtros cambiados seguidos se conservan.
let navegacion: Promise<unknown> = Promise.resolve()
function navegar(armar: () => Partial<FiltrosHistorial>) {
  navegacion = navegacion.then(() =>
    router.replace({
      query: Object.fromEntries(Object.entries(armar()).filter(([, v]) => v)),
    }),
  )
}

function filtrar(campo: keyof FiltrosHistorial, valor: string) {
  navegar(() => ({ ...filtros.value, [campo]: valor }))
}

function quitarFiltros() {
  navegar(() => ({}))
}

async function cargar() {
  solicitud?.abort()
  if (fechasInvalidas.value) {
    registros.value = []
    total.value = 0
    estado.value = 'lista'
    return
  }
  const actual = new AbortController()
  solicitud = actual
  estado.value = 'cargando'
  errorMas.value = ''
  try {
    const respuesta = await listarHistorial(filtros.value, 1, actual.signal)
    registros.value = respuesta.items
    total.value = respuesta.total
    pagina.value = 1
    estado.value = 'lista'
  } catch {
    if (actual.signal.aborted) return
    registros.value = []
    estado.value = 'error'
  }
}

async function mostrarMas() {
  if (cargandoMas.value) return
  cargandoMas.value = true
  errorMas.value = ''
  try {
    const respuesta = await listarHistorial(filtros.value, pagina.value + 1)
    // Si entraron registros nuevos entre páginas, uno puede repetirse: se muestra una vez.
    const vistos = new Set(registros.value.map((r) => r.id))
    registros.value.push(...respuesta.items.filter((r) => !vistos.has(r.id)))
    total.value = respuesta.total
    pagina.value += 1
  } catch {
    errorMas.value = 'No pudimos cargar más registros. Inténtalo otra vez.'
  } finally {
    cargandoMas.value = false
  }
}

async function exportar() {
  if (exportando.value) return
  exportando.value = true
  errorExportacion.value = ''
  try {
    const archivo = await exportarHistorial(filtros.value)
    const url = URL.createObjectURL(archivo)
    const enlace = document.createElement('a')
    enlace.href = url
    enlace.download = `historial-${hoy}.xlsx`
    document.body.append(enlace)
    enlace.click()
    enlace.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (fallo) {
    errorExportacion.value = (fallo as ErrorApi).detail || 'No pudimos exportar el historial.'
  } finally {
    exportando.value = false
  }
}

async function cargarPersonas() {
  const propias = sesion.usuario
    ? [{ valor: sesion.usuario.id, etiqueta: `Tú (${sesion.usuario.nombre})` }]
    : []
  personas.value = propias
  try {
    cuentas.value = await listarAsistentes()
    personas.value = [
      ...propias,
      ...cuentas.value.map((c) => ({ valor: c.id, etiqueta: nombreDe(c) })),
    ]
  } catch {
    // Sin la lista de asistentes el filtro sigue sirviendo para tus propias acciones.
  }
}

watch(() => route.query, cargar, { immediate: true })
onMounted(cargarPersonas)
onBeforeUnmount(() => solicitud?.abort())
</script>

<template>
  <div class="historial">
    <header class="encabezado">
      <div>
        <h1>Historial</h1>
        <p>Quién hizo qué y cuándo, en tu cuenta y en la de tu asistente.</p>
      </div>
      <Button
        label="Exportar a Excel"
        icon="pi pi-download"
        outlined
        :loading="exportando"
        :disabled="estado !== 'lista' || !total"
        @click="exportar"
      />
    </header>
    <p v-if="errorExportacion" class="aviso-error" role="alert">{{ errorExportacion }}</p>

    <form class="filtros" aria-label="Filtrar historial" @submit.prevent>
      <div class="filtro">
        <label for="historial-usuario">Persona</label>
        <select
          id="historial-usuario"
          :value="filtros.usuario"
          @change="filtrar('usuario', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">Todas</option>
          <option v-for="p in personas" :key="p.valor" :value="p.valor">{{ p.etiqueta }}</option>
          <option
            v-if="filtros.usuario && !personas.some((p) => p.valor === filtros.usuario)"
            :value="filtros.usuario"
          >
            {{ filtros.usuario }}
          </option>
        </select>
      </div>
      <div class="filtro">
        <label for="historial-accion">Acción</label>
        <select
          id="historial-accion"
          :value="filtros.accion"
          @change="filtrar('accion', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">Todas</option>
          <optgroup v-for="grupo in OPCIONES_ACCION" :key="grupo.grupo" :label="grupo.grupo">
            <option v-for="a in grupo.acciones" :key="a.valor" :value="a.valor">
              {{ a.etiqueta }}
            </option>
          </optgroup>
        </select>
      </div>
      <div class="filtro">
        <label for="historial-desde">Desde</label>
        <input
          id="historial-desde"
          type="date"
          :value="filtros.desde"
          :max="hoy"
          @change="filtrar('desde', ($event.target as HTMLInputElement).value)"
        />
      </div>
      <div class="filtro">
        <label for="historial-hasta">Hasta</label>
        <input
          id="historial-hasta"
          type="date"
          :value="filtros.hasta"
          :max="hoy"
          :aria-invalid="fechasInvalidas"
          :aria-describedby="fechasInvalidas ? 'historial-error-fechas' : undefined"
          @change="filtrar('hasta', ($event.target as HTMLInputElement).value)"
        />
      </div>
      <button v-if="hayFiltros" type="button" class="quitar" @click="quitarFiltros">
        Quitar filtros
      </button>
      <p v-if="fechasInvalidas" id="historial-error-fechas" class="error-campo" role="alert">
        La fecha final debe ser igual o posterior a la inicial.
      </p>
    </form>

    <div v-if="estado === 'cargando'" aria-busy="true">
      <p class="lector" role="status">Cargando historial…</p>
      <div class="marcador marcador--dia"></div>
      <div v-for="n in 5" :key="n" class="marcador marcador--fila"></div>
    </div>

    <div v-else-if="estado === 'error'" class="fallo" role="alert">
      <h2>No pudimos cargar el historial.</h2>
      <p>Revisa tu conexión e inténtalo otra vez. Tus filtros se conservan.</p>
      <Button label="Reintentar" icon="pi pi-refresh" @click="cargar" />
    </div>

    <section v-else-if="!registros.length" class="vacio" aria-live="polite">
      <template v-if="hayFiltros && !fechasInvalidas">
        <h2>Ningún registro coincide con estos filtros</h2>
        <p>Prueba con otra persona, otra acción u otras fechas.</p>
        <Button label="Quitar filtros" outlined @click="quitarFiltros" />
      </template>
      <template v-else-if="!hayFiltros">
        <h2>Todavía no hay acciones registradas</h2>
        <p>Aquí verás los ingresos, los cambios de tus deudas y lo que hagan tus asistentes.</p>
      </template>
    </section>

    <template v-else>
      <p class="conteo" role="status">
        {{ total === 1 ? '1 registro' : `${total.toLocaleString('es-PE')} registros` }}
        <template v-if="hayFiltros"> con estos filtros</template>
      </p>
      <section
        v-for="grupo in dias"
        :key="grupo.dia"
        class="dia"
        :aria-labelledby="`dia-${grupo.dia}`"
      >
        <h2 :id="`dia-${grupo.dia}`">{{ tituloDia(grupo.dia) }}</h2>
        <ul>
          <RegistroHistorial
            v-for="r in grupo.registros"
            :key="r.id"
            :registro="r"
            :nombres="nombres"
            :propio="r.usuario_id === sesion.usuario?.id"
          />
        </ul>
      </section>
      <div v-if="quedan > 0" class="mas">
        <Button
          :label="`Mostrar ${Math.min(quedan, TAMANO_PAGINA)} más`"
          outlined
          :loading="cargandoMas"
          @click="mostrarMas"
        />
        <span>Ves {{ registros.length }} de {{ total }}</span>
        <p v-if="errorMas" class="aviso-error" role="alert">{{ errorMas }}</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.historial {
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
/* Los filtros son una regla de la hoja, no una tarjeta más: se leen como el encabezado de la bitácora. */
.filtros {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1.4fr) repeat(2, minmax(0, 0.9fr)) auto;
  align-items: end;
  gap: 12px 16px;
  margin-bottom: 28px;
  padding: 16px 18px;
  border-radius: 5px 20px 5px 5px;
  background: var(--deconsta-paper-claro);
  box-shadow: inset 0 -2px 0 var(--deconsta-primary);
}
.filtro {
  display: grid;
  gap: 6px;
  min-width: 0;
}
.filtro label {
  font-size: var(--texto-sm);
  font-weight: 600;
}
.filtro select,
.filtro input {
  width: 100%;
  min-height: 42px;
  padding: 0 10px;
  border: 1px solid var(--deconsta-linea);
  border-radius: var(--radio-control);
  background: #fff;
  color: var(--deconsta-ink);
  font: inherit;
}
.filtro select:focus-visible,
.filtro input:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 1px;
}
.filtro input[aria-invalid='true'] {
  border-color: var(--deconsta-error);
}
.quitar {
  min-height: 42px;
  padding: 0 4px;
  border: 0;
  background: transparent;
  color: var(--deconsta-primary);
  font: inherit;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 4px;
  cursor: pointer;
}
.error-campo {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--deconsta-error);
  font-size: var(--texto-sm);
  font-weight: 600;
}
.conteo {
  margin: 0 0 8px;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.dia {
  margin-bottom: 28px;
}
.dia h2 {
  position: sticky;
  top: 0;
  z-index: 1;
  margin: 0;
  padding: 10px 0 8px;
  border-bottom: 1px solid var(--deconsta-ink);
  background: var(--deconsta-paper);
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-lg);
  font-weight: 500;
}
.dia ul {
  margin: 0;
  padding: 0;
  list-style: none;
}
.mas {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  padding-top: 8px;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.mas .aviso-error {
  flex-basis: 100%;
}
.aviso-error {
  margin: 0 0 16px;
  color: var(--deconsta-error);
  font-weight: 600;
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
  border-radius: var(--radio-control);
  background: linear-gradient(90deg, #e6ece9 0%, #f4f7f5 50%, #e6ece9 100%) 0 0 / 200% 100%;
  animation: brillo 1.4s ease-in-out infinite;
}
.marcador--dia {
  width: 160px;
  height: 28px;
  margin-bottom: 16px;
}
.marcador--fila {
  height: 58px;
  margin-bottom: 8px;
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
@media (max-width: 860px) {
  .filtros {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .quitar {
    justify-self: start;
  }
}
@media (max-width: 520px) {
  .encabezado :deep(.p-button) {
    width: 100%;
  }
  /* Persona y acción a lo ancho; las fechas lado a lado para que la bitácora asome antes. */
  .filtros {
    gap: 10px 12px;
    padding: 14px;
  }
  .filtro:nth-child(-n + 2) {
    grid-column: 1 / -1;
  }
  .filtro input {
    padding: 0 6px;
  }
}
</style>
