<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import LimitesSuperficie from '@/components/limites/LimitesSuperficie.vue'
import SolicitudesSuperficie from '@/components/limites/SolicitudesSuperficie.vue'
import {
  ESTADOS_SOLICITUD,
  monto,
  type ConsumoMes,
  type EstadoSolicitud,
  type Limites,
  type Solicitud,
} from '@/components/limites/modelo'
import {
  aprobarSolicitud,
  definirLimites,
  listarSolicitudes,
  obtenerLimites,
  rechazarSolicitud,
} from '@/api/limites'
import type { ErrorApi } from '@/types/api'

// H05 (TASK-25): límites con el consumo del mes y solicitudes de aprobación, sobre las
// superficies de TASK-21. El filtro de solicitudes vive en la URL (?ver=aprobada).
const route = useRoute()
const router = useRouter()
const toast = useToast()

const limites = ref<Limites | null>(null)
const consumo = ref<ConsumoMes | null>(null)
const estadoLimites = ref<'lista' | 'cargando' | 'error'>('cargando')

const solicitudes = ref<Solicitud[]>([])
const total = ref(0)
const pagina = ref(1)
const pendientes = ref(0)
const estadoSolicitudes = ref<'lista' | 'cargando' | 'error'>('cargando')
const cargandoMas = ref(false)
const ocupada = ref<string | null>(null)

const filtro = computed<EstadoSolicitud>(() => {
  const ver = route.query.ver
  return ESTADOS_SOLICITUD.some((e) => e.valor === ver) ? (ver as EstadoSolicitud) : 'pendiente'
})
const hayMas = computed(() => solicitudes.value.length < total.value)

async function cargarLimites(silencioso = false) {
  if (!silencioso) estadoLimites.value = 'cargando'
  try {
    const datos = await obtenerLimites()
    limites.value = { por_pago: datos.por_pago, mensual: datos.mensual }
    consumo.value = datos.consumo
    estadoLimites.value = 'lista'
  } catch {
    if (!silencioso || !limites.value) estadoLimites.value = 'error'
  }
}

async function cargarSolicitudes(silencioso = false) {
  if (!silencioso) estadoSolicitudes.value = 'cargando'
  const estado = filtro.value
  try {
    const [lista, porAprobar] = await Promise.all([
      listarSolicitudes(estado),
      estado === 'pendiente' ? null : listarSolicitudes('pendiente'),
    ])
    // Si el filtro cambió mientras llegaba la respuesta, la de ahora manda.
    if (estado !== filtro.value) return
    solicitudes.value = lista.items
    total.value = lista.total
    pagina.value = 1
    pendientes.value = (porAprobar ?? lista).total
    estadoSolicitudes.value = 'lista'
  } catch {
    if (!silencioso || !solicitudes.value.length) estadoSolicitudes.value = 'error'
  }
}

async function mostrarMas() {
  cargandoMas.value = true
  try {
    const siguiente = await listarSolicitudes(filtro.value, pagina.value + 1)
    const vistas = new Set(solicitudes.value.map((s) => s.id))
    solicitudes.value.push(...siguiente.items.filter((s) => !vistas.has(s.id)))
    total.value = siguiente.total
    pagina.value += 1
  } catch {
    toast.add({
      severity: 'error',
      summary: 'No pudimos cargar más solicitudes',
      detail: 'Inténtalo otra vez.',
      life: 5000,
    })
  } finally {
    cargandoMas.value = false
  }
}

function filtrar(estado: EstadoSolicitud) {
  void router.replace({
    query: { ...route.query, ver: estado === 'pendiente' ? undefined : estado },
  })
}

async function guardar(valores: Record<string, unknown>) {
  const datos = await definirLimites(valores)
  limites.value = { por_pago: datos.por_pago, mensual: datos.mensual }
  consumo.value = datos.consumo
}

async function resolver(
  id: string,
  accion: () => Promise<Solicitud>,
  exito: (s: Solicitud) => { summary: string; detail: string },
) {
  if (ocupada.value) return
  ocupada.value = id
  try {
    const resuelta = await accion()
    toast.add({ severity: 'success', life: 5000, ...exito(resuelta) })
  } catch (fallo) {
    const error = fallo as ErrorApi
    toast.add({
      severity: error.status === 409 ? 'warn' : 'error',
      summary: error.status === 409 ? 'La solicitud ya cambió' : 'No pudimos responder',
      detail: error.detail || 'Revisa tu conexión e inténtalo otra vez.',
      life: 6000,
    })
  } finally {
    ocupada.value = null
    // Resuelta o no, la lista y el contador se leen otra vez: otra pestaña pudo responderla.
    await cargarSolicitudes(true)
  }
}

function aprobar(id: string) {
  void resolver(
    id,
    () => aprobarSolicitud(id),
    (s) => ({
      summary: 'Pago aprobado',
      detail: `${s.asistente} ya puede pagar ${monto(s.monto, s.moneda)} de ${s.servicio}.`,
    }),
  )
}

function rechazar(id: string, motivo: string | null) {
  void resolver(
    id,
    () => rechazarSolicitud(id, motivo),
    (s) => ({
      summary: 'Solicitud rechazada',
      detail: `Le avisamos a ${s.asistente}.`,
    }),
  )
}

// Al volver a la pestaña puede haber solicitudes nuevas o un consumo distinto.
function alVolver() {
  if (document.visibilityState !== 'visible') return
  void cargarSolicitudes(true)
  void cargarLimites(true)
}

watch(filtro, () => cargarSolicitudes())
onMounted(() => {
  void cargarLimites()
  void cargarSolicitudes()
  document.addEventListener('visibilitychange', alVolver)
})
onBeforeUnmount(() => document.removeEventListener('visibilitychange', alVolver))
</script>

<template>
  <div class="limites-pagina">
    <header class="encabezado">
      <h1>Límites y aprobaciones</h1>
      <p>Decide hasta cuánto puede pagar tu asistente sin pedirte permiso.</p>
    </header>
    <LimitesSuperficie
      :limites="limites"
      :consumo="consumo"
      :estado-pantalla="estadoLimites"
      :guardar="guardar"
      @reintentar="cargarLimites()"
    />
    <div class="separador"></div>
    <SolicitudesSuperficie
      :solicitudes="solicitudes"
      :filtro="filtro"
      :pendientes="pendientes"
      :estado-pantalla="estadoSolicitudes"
      :ocupada="ocupada"
      :hay-mas="hayMas"
      :cargando-mas="cargandoMas"
      @filtrar="filtrar"
      @aprobar="aprobar"
      @rechazar="rechazar"
      @reintentar="cargarSolicitudes()"
      @mas="mostrarMas"
    />
  </div>
</template>

<style scoped>
.limites-pagina {
  max-width: 1120px;
}
.encabezado {
  max-width: 62ch;
  margin-bottom: clamp(28px, 4vw, 44px);
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
.separador {
  height: 1px;
  margin: clamp(36px, 5vw, 56px) 0 clamp(28px, 4vw, 40px);
  background: var(--deconsta-linea);
}
</style>
