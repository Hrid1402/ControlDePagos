<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { CategoriaCalendario, DiaCalendario, VistaCalendario } from './modelo'
import {
  claveFecha,
  DIAS_SEMANA,
  fechaLarga,
  fechasVisibles,
  moverPeriodo,
  tituloPeriodo,
} from './fechas'

const props = withDefaults(
  defineProps<{
    dias?: DiaCalendario[]
    categorias?: CategoriaCalendario[]
    estadoPantalla?: 'lista' | 'cargando' | 'error'
    exportable?: boolean
  }>(),
  { dias: () => [], categorias: () => [], estadoPantalla: 'lista', exportable: false },
)

const emit = defineEmits<{
  filtrar: [filtros: { categoria: string; estado: string }]
  exportar: []
  reintentar: []
  abrirDeuda: [id: string]
  periodo: [desde: string, hasta: string]
}>()

const hoy = new Date()
const fecha = ref(new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate()))
const diaSeleccionado = ref(claveFecha(fecha.value))
const vista = ref<VistaCalendario>('mes')
const categoria = ref('')
const estado = ref('')

onMounted(() => {
  if (window.matchMedia('(max-width: 767px)').matches) vista.value = 'lista'
})

const fechas = computed(() => fechasVisibles(fecha.value, vista.value))
const diasPorFecha = computed(() => new Map(props.dias.map((dia) => [dia.fecha, dia])))
const diaActivo = computed(() => diasPorFecha.value.get(diaSeleccionado.value))
const fechaActiva = computed(() => {
  const [anio = 0, mes = 1, dia = 1] = diaSeleccionado.value.split('-').map(Number)
  return new Date(anio, mes - 1, dia)
})
const totalVencimientos = computed(() => props.dias.reduce((total, dia) => total + dia.deudas.length, 0))

watch(
  [fechas, categoria, estado],
  () => {
    const primera = fechas.value[0]
    const ultima = fechas.value.at(-1)
    if (primera && ultima) emit('periodo', claveFecha(primera), claveFecha(ultima))
    emit('filtrar', { categoria: categoria.value, estado: estado.value })
  },
  { immediate: true },
)

function navegar(direccion: number) {
  fecha.value = moverPeriodo(fecha.value, vista.value, direccion)
  diaSeleccionado.value = claveFecha(fecha.value)
}

function irHoy() {
  fecha.value = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate())
  diaSeleccionado.value = claveFecha(fecha.value)
}

function elegirDia(fechaElegida: Date) {
  diaSeleccionado.value = claveFecha(fechaElegida)
  fecha.value = fechaElegida
}

function nombreEstado(valor: string): string {
  if (valor === 'esperando_recibo') return 'Esperando recibo'
  if (valor === 'vencida') return 'Vencida'
  if (valor === 'pagada') return 'Pagada'
  return 'Pendiente'
}

function colorEstado(valor: string): string {
  if (valor === 'esperando_recibo') return 'esperando'
  if (valor === 'vencida') return 'vencida'
  if (valor === 'pagada') return 'pagada'
  return 'pendiente'
}

function moneda(valor: string, codigo: string): string {
  return `${codigo === 'PEN' ? 'S/' : '$'} ${valor}`
}
</script>

<template>
  <section class="calendario" aria-labelledby="titulo-calendario">
    <header class="encabezado">
      <div>
        <h1 id="titulo-calendario">Calendario</h1>
        <p>Consulta los vencimientos y organiza los pagos con tiempo.</p>
      </div>
      <button class="exportar" type="button" :disabled="!exportable" @click="emit('exportar')">
        <i class="pi pi-download" aria-hidden="true"></i>
        Exportar calendario
      </button>
    </header>

    <div class="barra" aria-label="Controles del calendario">
      <div class="periodo">
        <div class="flechas" aria-label="Navegar fechas">
          <button type="button" aria-label="Periodo anterior" @click="navegar(-1)">
            <i class="pi pi-chevron-left" aria-hidden="true"></i>
          </button>
          <button type="button" aria-label="Periodo siguiente" @click="navegar(1)">
            <i class="pi pi-chevron-right" aria-hidden="true"></i>
          </button>
        </div>
        <h2>{{ tituloPeriodo(fecha, vista) }}</h2>
        <button class="hoy" type="button" @click="irHoy">Hoy</button>
      </div>
      <div class="vistas" role="group" aria-label="Vista del calendario">
        <button
          v-for="opcion in (['mes', 'semana', 'lista'] as const)"
          :key="opcion"
          type="button"
          :aria-pressed="vista === opcion"
          :class="{ activa: vista === opcion }"
          @click="vista = opcion"
        >
          {{ opcion === 'mes' ? 'Mes' : opcion === 'semana' ? 'Semana' : 'Lista' }}
        </button>
      </div>
    </div>

    <div class="filtros">
      <div class="filtro">
        <label for="calendario-categoria">Categoría</label>
        <select id="calendario-categoria" v-model="categoria">
          <option value="">Todas las categorías</option>
          <option v-for="opcion in categorias" :key="opcion.id" :value="opcion.id">
            {{ opcion.nombre }}
          </option>
        </select>
      </div>
      <div class="filtro">
        <label for="calendario-estado">Estado</label>
        <select id="calendario-estado" v-model="estado">
          <option value="">Todos los estados</option>
          <option value="pendiente">Pendiente</option>
          <option value="pagada">Pagada</option>
          <option value="vencida">Vencida</option>
          <option value="esperando_recibo">Esperando recibo</option>
        </select>
      </div>
      <p class="conteo" role="status">
        {{ totalVencimientos }} {{ totalVencimientos === 1 ? 'vencimiento' : 'vencimientos' }}
      </p>
    </div>

    <div v-if="estadoPantalla === 'error'" class="mensaje error" role="alert">
      <i class="pi pi-exclamation-circle" aria-hidden="true"></i>
      <div>
        <h2>No pudimos cargar el calendario</h2>
        <p>Revisa tu conexión e inténtalo de nuevo. Tus filtros se conservarán.</p>
        <button type="button" @click="emit('reintentar')">Reintentar</button>
      </div>
    </div>
    <div v-else-if="estadoPantalla === 'cargando'" class="cargando" aria-busy="true">
      <p role="status">Cargando vencimientos…</p>
      <div class="esqueleto"></div>
    </div>
    <div v-else class="cuerpo" :class="{ 'cuerpo--lista': vista === 'lista' }">
      <div class="tablero">
        <div v-if="vista !== 'lista'" class="rejilla" :class="{ 'rejilla--semana': vista === 'semana' }">
          <div v-for="nombre in DIAS_SEMANA" :key="nombre" class="nombre-dia">{{ nombre }}</div>
          <button
            v-for="dia in fechas"
            :key="claveFecha(dia)"
            class="celda"
            :class="{
              'celda--ajena': dia.getMonth() !== fecha.getMonth() && vista === 'mes',
              'celda--hoy': claveFecha(dia) === claveFecha(hoy),
              'celda--activa': claveFecha(dia) === diaSeleccionado,
            }"
            type="button"
            :aria-label="`${fechaLarga(dia)}: ${diasPorFecha.get(claveFecha(dia))?.deudas.length || 0} vencimientos`"
            :aria-pressed="claveFecha(dia) === diaSeleccionado"
            @click="elegirDia(dia)"
          >
            <span class="numero">{{ dia.getDate() }}</span>
            <span v-if="diasPorFecha.get(claveFecha(dia))?.deudas.length" class="marcas">
              <span
                v-for="deuda in diasPorFecha.get(claveFecha(dia))?.deudas.slice(0, 3)"
                :key="deuda.id"
                class="marca-estado"
                :class="`marca-estado--${colorEstado(deuda.estado)}`"
              ></span>
            </span>
            <span v-if="diasPorFecha.get(claveFecha(dia))?.totales_confirmados.PEN" class="monto-dia">
              {{ moneda(diasPorFecha.get(claveFecha(dia))!.totales_confirmados.PEN!, 'PEN') }}
            </span>
          </button>
        </div>
        <div v-else class="lista-fechas">
          <button
            v-for="dia in fechas"
            :key="claveFecha(dia)"
            type="button"
            class="fila-fecha"
            :class="{ 'fila-fecha--activa': claveFecha(dia) === diaSeleccionado }"
            :aria-pressed="claveFecha(dia) === diaSeleccionado"
            @click="elegirDia(dia)"
          >
            <span class="fecha-lista">
              <strong>{{ dia.getDate() }}</strong>
              <span>{{ fechaLarga(dia) }}</span>
            </span>
            <span class="resumen-lista">
              {{ diasPorFecha.get(claveFecha(dia))?.deudas.length || 0 }}
              {{ diasPorFecha.get(claveFecha(dia))?.deudas.length === 1 ? 'deuda' : 'deudas' }}
            </span>
            <i class="pi pi-chevron-right" aria-hidden="true"></i>
          </button>
        </div>
      </div>

      <aside class="detalle" aria-label="Deudas del día seleccionado">
        <header class="detalle-cabecera">
          <div>
            <p class="detalle-contexto">Día seleccionado</p>
            <h2>{{ fechaLarga(fechaActiva) }}</h2>
          </div>
          <span class="detalle-conteo">{{ diaActivo?.deudas.length || 0 }}</span>
        </header>
        <div v-if="diaActivo?.deudas.length" class="deudas">
          <button
            v-for="deuda in diaActivo.deudas"
            :key="deuda.id"
            type="button"
            class="deuda"
            @click="emit('abrirDeuda', deuda.id)"
          >
            <span class="deuda-principal">
              <strong>{{ deuda.nombre }}</strong>
              <span class="estado" :class="`estado--${colorEstado(deuda.estado)}`">
                {{ nombreEstado(deuda.estado) }}
              </span>
            </span>
            <span class="deuda-monto">
              {{ deuda.monto ? moneda(deuda.monto, deuda.moneda) : 'Importe por confirmar' }}
              <i class="pi pi-arrow-up-right" aria-hidden="true"></i>
            </span>
          </button>
          <div class="totales" aria-label="Totales del día">
            <p v-for="(valor, codigo) in diaActivo.totales_confirmados" :key="codigo">
              <span>Total confirmado · {{ codigo }}</span><strong>{{ moneda(valor, codigo) }}</strong>
            </p>
            <p v-for="(valor, codigo) in diaActivo.totales_proyectados" :key="codigo">
              <span>Proyección sin recibo · {{ codigo }}</span><strong>{{ moneda(valor, codigo) }}</strong>
            </p>
          </div>
        </div>
        <div v-else class="sin-deudas">
          <i class="pi pi-calendar" aria-hidden="true"></i>
          <h3>Sin vencimientos este día</h3>
          <p>Elige otra fecha para revisar los pagos previstos.</p>
        </div>
      </aside>
    </div>
    <footer class="leyenda" aria-label="Estados de las deudas">
      <span v-for="clave in ['pendiente', 'pagada', 'vencida', 'esperando_recibo']" :key="clave">
        <i class="marca-estado" :class="`marca-estado--${colorEstado(clave)}`" aria-hidden="true"></i>
        {{ nombreEstado(clave) }}
      </span>
    </footer>
  </section>
</template>
