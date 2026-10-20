<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import FullCalendar from '@fullcalendar/vue3'
import dayGridPlugin from '@fullcalendar/daygrid'
import interactionPlugin, { type DateClickArg } from '@fullcalendar/interaction'
import listPlugin from '@fullcalendar/list'
import esLocale from '@fullcalendar/core/locales/es'
import type { CalendarOptions, DatesSetArg, EventClickArg } from '@fullcalendar/core'
import type { CategoriaCalendario, DiaCalendario, VistaCalendario } from './modelo'
import { claveFecha, fechaLarga, fechaLocal, hoyLima, sumarDias } from './fechas'
import type { FiltrosCalendario } from '@/api/calendario'

const props = withDefaults(
  defineProps<{
    dias?: DiaCalendario[]
    categorias?: CategoriaCalendario[]
    estadoPantalla?: 'lista' | 'cargando' | 'error'
    mensajeError?: string
    exportable?: boolean
    exportando?: boolean
  }>(),
  {
    dias: () => [],
    categorias: () => [],
    estadoPantalla: 'lista',
    mensajeError: '',
    exportable: false,
    exportando: false,
  },
)
const emit = defineEmits<{
  consultar: [filtros: FiltrosCalendario]
  exportar: []
  reintentar: []
  abrirDeuda: [id: string]
}>()

const calendario = ref<InstanceType<typeof FullCalendar> | null>(null)
const diaSeleccionado = ref(hoyLima())
const vista = ref<VistaCalendario>(
  typeof window !== 'undefined' && window.matchMedia?.('(max-width: 767px)').matches
    ? 'lista'
    : 'mes',
)
const vistaInicial = vista.value
const titulo = ref('')
const desde = ref('')
const hasta = ref('')
const categoria = ref('')
const estado = ref('')
const vistas = { mes: 'dayGridMonth', semana: 'dayGridWeek', lista: 'listMonth' }
const diasPorFecha = computed(() => new Map(props.dias.map((dia) => [dia.fecha, dia])))
const diaActivo = computed(() => diasPorFecha.value.get(diaSeleccionado.value))
const totalVencimientos = computed(() => props.dias.reduce((n, dia) => n + dia.deudas.length, 0))

function consultar() {
  if (desde.value && hasta.value)
    emit('consultar', {
      desde: desde.value,
      hasta: hasta.value,
      categoria: categoria.value,
      estado: estado.value,
    })
}
watch([categoria, estado], consultar)

function rangoCambiado(info: DatesSetArg) {
  titulo.value = info.view.title.charAt(0).toUpperCase() + info.view.title.slice(1)
  vista.value =
    info.view.type === 'dayGridWeek' ? 'semana' : info.view.type === 'listMonth' ? 'lista' : 'mes'
  desde.value = claveFecha(info.start)
  hasta.value = claveFecha(sumarDias(info.end, -1))
  if (diaSeleccionado.value < desde.value || diaSeleccionado.value > hasta.value)
    diaSeleccionado.value = claveFecha(info.view.currentStart)
  consultar()
}

function seleccionarDia(info: DateClickArg) {
  diaSeleccionado.value = info.dateStr.slice(0, 10)
}
function seleccionarDeuda(info: EventClickArg) {
  info.jsEvent.preventDefault()
  if (info.event.start) diaSeleccionado.value = claveFecha(info.event.start)
  emit('abrirDeuda', info.event.id)
}
function nombreEstado(valor: string): string {
  const nombres: Record<string, string> = {
    esperando_recibo: 'Esperando recibo',
    esperando_aprobacion: 'Esperando aprobación',
    en_proceso: 'En proceso',
    por_validar: 'Por validar',
    pagada_parcial: 'Pagada parcial',
    con_problema: 'Con problema',
    vencida: 'Vencida',
    pagada: 'Pagada',
    pendiente: 'Pendiente',
  }
  return nombres[valor] || 'Pendiente'
}
function colorEstado(valor: string): string {
  if (valor === 'esperando_recibo') return 'esperando'
  if (valor === 'vencida') return 'vencida'
  if (valor === 'pagada') return 'pagada'
  return 'pendiente'
}
function moneda(valor: string, codigo: string): string {
  return (codigo === 'PEN' ? 'S/ ' : '$ ') + valor
}

const opciones = computed<CalendarOptions>(() => {
  const seleccion = diaSeleccionado.value
  return {
    plugins: [dayGridPlugin, interactionPlugin, listPlugin],
    locale: esLocale,
    initialDate: hoyLima(),
    initialView: vistas[vistaInicial],
    firstDay: 1,
    headerToolbar: false,
    height: 'auto',
    fixedWeekCount: false,
    dayMaxEvents: 3,
    navLinks: true,
    navLinkDayClick: (fecha) => {
      diaSeleccionado.value = claveFecha(fecha)
    },
    navLinkHint: 'Ver deudas de $0',
    displayEventTime: false,
    noEventsContent: 'Sin vencimientos en este periodo',
    datesSet: rangoCambiado,
    dateClick: seleccionarDia,
    eventClick: seleccionarDeuda,
    events: props.dias.flatMap((dia) =>
      dia.deudas.map((deuda) => ({
        id: deuda.id,
        title: deuda.nombre,
        start: deuda.fecha_vencimiento,
        allDay: true,
        classNames: ['fc-deuda--' + colorEstado(deuda.estado)],
        extendedProps: { estado: deuda.estado },
      })),
    ),
    eventDidMount: (info) => {
      info.el.setAttribute(
        'aria-label',
        info.event.title + ', ' + nombreEstado(String(info.event.extendedProps.estado)),
      )
    },
    dayCellClassNames: (info) => {
      const fecha = claveFecha(info.date)
      return [
        fecha === seleccion ? 'fc-dia--activo' : '',
        diasPorFecha.value.has(fecha) ? 'fc-dia--con-deudas' : '',
      ].filter(Boolean)
    },
    dayCellContent: (info) => {
      const contenido = document.createElement('span')
      contenido.className = 'fc-dia-cabecera'
      const numero = document.createElement('span')
      numero.textContent = info.dayNumberText
      contenido.append(numero)
      const dia = diasPorFecha.value.get(claveFecha(info.date))
      if (dia)
        for (const [codigo, valor] of Object.entries(dia.totales_confirmados)) {
          if (!valor) continue
          const total = document.createElement('span')
          total.className = 'fc-dia-total'
          total.textContent = moneda(valor, codigo)
          contenido.append(total)
        }
      return { domNodes: [contenido] }
    },
  }
})
function navegar(direccion: number) {
  if (direccion < 0) calendario.value?.getApi().prev()
  else calendario.value?.getApi().next()
}
function irHoy() {
  const fecha = hoyLima()
  calendario.value?.getApi().gotoDate(fecha)
  diaSeleccionado.value = fecha
}
function cambiarVista(nueva: VistaCalendario) {
  calendario.value?.getApi().changeView(vistas[nueva])
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
        {{ exportando ? 'Preparando archivo…' : 'Exportar calendario' }}
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
        <h2>{{ titulo }}</h2>
        <button class="hoy" type="button" @click="irHoy">Hoy</button>
      </div>
      <div class="vistas" role="group" aria-label="Vista del calendario">
        <button
          v-for="opcion in ['mes', 'semana', 'lista'] as const"
          :key="opcion"
          type="button"
          :aria-pressed="vista === opcion"
          :class="{ activa: vista === opcion }"
          @click="cambiarVista(opcion)"
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
    <div class="cuerpo">
      <div class="tablero" :aria-busy="estadoPantalla === 'cargando'">
        <FullCalendar ref="calendario" :options="opciones" />
        <div v-if="estadoPantalla === 'cargando'" class="calendario-capa" role="status">
          Cargando vencimientos…
        </div>
        <div
          v-else-if="estadoPantalla === 'error'"
          class="calendario-capa calendario-capa--error"
          role="alert"
        >
          <h2>No pudimos cargar el calendario</h2>
          <p>
            {{ mensajeError || 'Revisa tu conexión e inténtalo de nuevo.' }} Tus filtros se
            conservarán.
          </p>
          <button type="button" @click="emit('reintentar')">Reintentar</button>
        </div>
      </div>
      <aside class="detalle" aria-label="Deudas del día seleccionado">
        <header class="detalle-cabecera">
          <div>
            <p class="detalle-contexto">Día seleccionado</p>
            <h2>{{ fechaLarga(fechaLocal(diaSeleccionado)) }}</h2>
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
            <span class="deuda-principal"
              ><strong>{{ deuda.nombre }}</strong>
              <span class="estado" :class="'estado--' + colorEstado(deuda.estado)">{{
                nombreEstado(deuda.estado)
              }}</span>
            </span>
            <span class="deuda-monto">
              {{
                deuda.monto
                  ? moneda(deuda.monto, deuda.moneda)
                  : deuda.monto_proyectado
                    ? moneda(deuda.monto_proyectado, deuda.moneda) + ' estimado'
                    : 'Importe por confirmar'
              }}
              <i class="pi pi-arrow-up-right" aria-hidden="true"></i>
            </span>
          </button>
          <div class="totales" aria-label="Totales del día">
            <p v-for="(valor, codigo) in diaActivo.totales_confirmados" :key="codigo">
              <span>Total confirmado · {{ codigo }}</span
              ><strong>{{ moneda(valor ?? '0.00', codigo) }}</strong>
            </p>
            <p v-for="(valor, codigo) in diaActivo.totales_proyectados" :key="codigo">
              <span>Proyección sin recibo · {{ codigo }}</span
              ><strong>{{ moneda(valor ?? '0.00', codigo) }}</strong>
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
        <i
          class="marca-estado"
          :class="'marca-estado--' + colorEstado(clave)"
          aria-hidden="true"
        ></i
        >{{ nombreEstado(clave) }}
      </span>
    </footer>
  </section>
</template>

<style scoped src="./calendario.css"></style>
