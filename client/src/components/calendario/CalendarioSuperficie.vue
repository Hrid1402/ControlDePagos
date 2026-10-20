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

<style scoped>
.calendario {
  --cal-linea: #ccd8d2;
  --cal-superficie: #fff;
  --cal-pendiente: #8a5800;
  --cal-pagada: #17654d;
  --cal-vencida: #a12e3e;
  --cal-esperando: #4c6581;
  max-width: 1500px;
  margin-inline: auto;
}

.encabezado {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
  margin-bottom: clamp(30px, 4vw, 48px);
}
.encabezado h1 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-xl);
  font-weight: 500;
  letter-spacing: -0.025em;
  line-height: 1.15;
}
.encabezado p {
  margin: 10px 0 0;
  color: var(--deconsta-muted);
  line-height: 1.6;
}
button,
select {
  cursor: pointer;
}
button:focus-visible,
select:focus-visible {
  outline: 3px solid var(--deconsta-primary);
  outline-offset: 3px;
}
.exportar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 44px;
  padding: 10px 18px;
  border: 1px solid var(--deconsta-primary);
  border-radius: var(--radio-control);
  background: var(--deconsta-primary);
  color: white;
  font-size: var(--texto-sm);
  font-weight: 700;
  white-space: nowrap;
}
.exportar:hover:not(:disabled) {
  background: var(--deconsta-primary-hondo);
}
.exportar:disabled {
  border-color: var(--cal-linea);
  background: var(--deconsta-realce);
  color: var(--deconsta-muted);
  cursor: not-allowed;
}
.barra {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--cal-linea);
}
.periodo {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.periodo h2 {
  min-width: 0;
  margin: 0 8px;
  font-size: clamp(1.125rem, 1rem + 0.45vw, 1.375rem);
  font-weight: 700;
  letter-spacing: -0.025em;
  white-space: nowrap;
}
.flechas {
  display: inline-flex;
  border: 1px solid var(--cal-linea);
  border-radius: var(--radio-control);
  background: var(--cal-superficie);
}
.flechas button {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border: 0;
  background: transparent;
  color: var(--deconsta-ink);
}
.flechas button + button {
  border-left: 1px solid var(--cal-linea);
}
.flechas button:hover,
.hoy:hover,
.vistas button:hover:not(.activa) {
  background: var(--deconsta-realce);
}
.hoy {
  min-height: 44px;
  padding: 0 14px;
  border: 1px solid var(--cal-linea);
  border-radius: var(--radio-control);
  background: var(--cal-superficie);
  color: var(--deconsta-primary);
  font-size: var(--texto-sm);
  font-weight: 700;
}
.vistas {
  display: inline-flex;
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--cal-linea);
  border-radius: 10px;
  background: var(--deconsta-realce);
}
.vistas button {
  min-width: 68px;
  min-height: 38px;
  padding: 0 12px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  font-weight: 650;
}
.vistas .activa {
  background: var(--cal-superficie);
  color: var(--deconsta-primary-hondo);
  box-shadow: 0 2px 6px rgb(13 62 50 / 9%);
}
.filtros {
  display: flex;
  align-items: end;
  gap: 14px;
  padding: 20px 0 26px;
}
.filtro {
  display: grid;
  gap: 7px;
  min-width: 180px;
}
.filtro label {
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
  font-weight: 700;
}
.filtro select {
  min-height: 44px;
  padding: 0 36px 0 12px;
  border: 1px solid #91a99e;
  border-radius: var(--radio-control);
  background: var(--cal-superficie);
  color: var(--deconsta-ink);
  font-size: var(--texto-sm);
}
.conteo {
  margin: 0 0 12px auto;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  white-space: nowrap;
}
.cuerpo {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 330px);
  gap: clamp(24px, 3vw, 44px);
  align-items: start;
}
.tablero {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--cal-linea);
  border-radius: 10px;
  background: var(--cal-superficie);
}
.rejilla {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
}
.nombre-dia {
  padding: 13px 8px;
  border-bottom: 1px solid var(--cal-linea);
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
  font-weight: 700;
  text-align: center;
}
.celda {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
  min-height: clamp(76px, 8vw, 112px);
  padding: 11px;
  border: 0;
  border-right: 1px solid #e2e9e5;
  border-bottom: 1px solid #e2e9e5;
  background: var(--cal-superficie);
  color: var(--deconsta-ink);
  text-align: left;
}
.celda:nth-child(7n) {
  border-right: 0;
}
.celda:hover {
  background: #f3f8f5;
}
.celda--ajena {
  background: #f7f9f7;
  color: var(--deconsta-muted);
}
.celda--activa,
.celda--activa:hover {
  background: #e3eeea;
  box-shadow: inset 0 0 0 2px var(--deconsta-primary);
}
.numero {
  display: grid;
  place-items: center;
  width: 29px;
  height: 29px;
  border-radius: 50%;
  font-size: var(--texto-sm);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.celda--hoy .numero {
  background: var(--deconsta-primary);
  color: white;
}
.marcas {
  display: inline-flex;
  gap: 4px;
}
.marca-estado {
  display: inline-block;
  width: 8px;
  height: 8px;
  flex: none;
  border-radius: 50%;
  background: var(--cal-pendiente);
}
.marca-estado--pagada {
  background: var(--cal-pagada);
}
.marca-estado--vencida {
  background: var(--cal-vencida);
}
.marca-estado--esperando {
  background: var(--cal-esperando);
}
.monto-dia {
  overflow: hidden;
  max-width: 100%;
  margin-top: auto;
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
  font-variant-numeric: tabular-nums;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rejilla--semana .celda {
  min-height: 260px;
}
.detalle {
  min-width: 0;
  padding-top: 6px;
}
.detalle-cabecera {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--cal-linea);
}
.detalle-contexto {
  margin: 0 0 5px;
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
  font-weight: 700;
}
.detalle h2 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-lg);
  font-weight: 500;
  line-height: 1.25;
}
.detalle-conteo {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex: none;
  border-radius: 50%;
  background: var(--deconsta-realce);
  color: var(--deconsta-primary-hondo);
  font-size: var(--texto-sm);
  font-weight: 800;
}
.sin-deudas {
  padding: 44px 12px;
  color: var(--deconsta-muted);
  text-align: center;
}
.sin-deudas > i {
  display: inline-grid;
  place-items: center;
  width: 54px;
  height: 54px;
  margin-bottom: 18px;
  border-radius: 50%;
  background: var(--deconsta-realce);
  color: var(--deconsta-primary);
  font-size: 21px;
}
.sin-deudas h3 {
  margin: 0;
  color: var(--deconsta-ink);
  font-size: var(--texto-base);
}
.sin-deudas p {
  max-width: 27ch;
  margin: 8px auto 0;
  font-size: var(--texto-sm);
  line-height: 1.55;
}
.deuda {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 18px 0;
  border: 0;
  border-bottom: 1px solid var(--cal-linea);
  background: transparent;
  color: var(--deconsta-ink);
  text-align: left;
}
.deuda:hover strong {
  color: var(--deconsta-primary);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.deuda-principal {
  display: grid;
  gap: 7px;
  min-width: 0;
}
.deuda-principal strong {
  font-size: var(--texto-sm);
}
.estado {
  color: var(--cal-pendiente);
  font-size: var(--texto-xs);
  font-weight: 700;
}
.estado--pagada {
  color: var(--cal-pagada);
}
.estado--vencida {
  color: var(--cal-vencida);
}
.estado--esperando {
  color: var(--cal-esperando);
}
.deuda-monto {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--deconsta-ink);
  font-size: var(--texto-xs);
  font-weight: 700;
  white-space: nowrap;
}
.deuda-monto i {
  color: var(--deconsta-primary);
}
.totales {
  padding-top: 18px;
}
.totales p {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin: 0 0 12px;
  font-size: var(--texto-sm);
}
.totales strong {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.lista-fechas {
  display: grid;
}
.fila-fecha {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
  min-height: 76px;
  padding: 12px 18px;
  border: 0;
  border-bottom: 1px solid var(--cal-linea);
  background: var(--cal-superficie);
  color: var(--deconsta-ink);
  text-align: left;
}
.fila-fecha:last-child {
  border-bottom: 0;
}
.fila-fecha:hover,
.fila-fecha--activa {
  background: var(--deconsta-realce);
}
.fecha-lista {
  display: flex;
  align-items: center;
  gap: 15px;
  min-width: 0;
  flex: 1;
}
.fecha-lista strong {
  font-family: Literata, Georgia, serif;
  font-size: 1.65rem;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.fecha-lista span {
  overflow: hidden;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.resumen-lista {
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
  white-space: nowrap;
}
.fila-fecha i {
  color: var(--deconsta-primary);
  font-size: 13px;
}
.leyenda {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 26px;
  padding-top: 24px;
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
}
.leyenda span {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.mensaje {
  display: flex;
  gap: 18px;
  max-width: 650px;
  padding: 24px;
  background: var(--deconsta-error-fondo);
  color: var(--deconsta-ink);
}
.mensaje > i {
  color: var(--deconsta-error);
  font-size: 24px;
}
.mensaje h2 {
  margin: 0;
  font-size: var(--texto-md);
}
.mensaje p {
  line-height: 1.55;
}
.mensaje button {
  min-height: 44px;
  padding: 8px 16px;
  border: 1px solid var(--deconsta-primary);
  border-radius: var(--radio-control);
  background: var(--deconsta-primary);
  color: white;
  font-weight: 700;
}
.cargando p {
  color: var(--deconsta-muted);
}
.esqueleto {
  height: 360px;
  border-radius: 10px;
  background: var(--deconsta-realce);
}
@media (max-width: 1100px) {
  .cuerpo {
    grid-template-columns: minmax(0, 1fr);
  }
  .detalle {
    padding-top: 8px;
  }
  .sin-deudas {
    padding: 30px 12px;
  }
}
@media (max-width: 767px) {
  .encabezado {
    flex-direction: column;
    gap: 18px;
  }
  .exportar {
    width: 100%;
  }
  .barra {
    align-items: flex-start;
    flex-direction: column;
    gap: 18px;
  }
  .periodo {
    flex-wrap: wrap;
    width: 100%;
  }
  .periodo h2 {
    margin: 0;
    flex: 1;
  }
  .vistas {
    width: 100%;
  }
  .vistas button {
    flex: 1;
  }
  .filtros {
    flex-wrap: wrap;
  }
  .filtro {
    min-width: min(100%, 180px);
    flex: 1;
  }
  .conteo {
    width: 100%;
    margin: 0;
  }
  .rejilla .celda {
    min-height: 68px;
    padding: 5px;
  }
  .numero {
    width: 26px;
    height: 26px;
  }
  .monto-dia {
    display: none;
  }
  .nombre-dia {
    padding: 10px 2px;
  }
  .rejilla--semana .celda {
    min-height: 130px;
  }
}
@media (max-width: 440px) {
  .periodo h2 {
    order: -1;
    width: 100%;
    flex: auto;
  }
  .filtro {
    min-width: 100%;
  }
  .fecha-lista span {
    max-width: 18ch;
  }
}
</style>
