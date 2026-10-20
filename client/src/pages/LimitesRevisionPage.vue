<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import LimitesSuperficie from '@/components/limites/LimitesSuperficie.vue'
import SolicitudesSuperficie from '@/components/limites/SolicitudesSuperficie.vue'
import type { EstadoSolicitud, Limites, Moneda, Solicitud } from '@/components/limites/modelo'

// Solo en desarrollo (/revision/limites). Quien revisa escribe los valores que quiere ver: la
// página no trae datos propios. La conexión con la API es TASK-25.
const estadoLimites = ref<'lista' | 'cargando' | 'error'>('lista')
const estadoSolicitudes = ref<'lista' | 'cargando' | 'error'>('lista')
const limites = ref<Limites>({ por_pago: null, mensual: null })
const consumo = reactive({ validado: '0', reservado: '0' })
const solicitudes = ref<Solicitud[]>([])
const filtro = ref<EstadoSolicitud>('pendiente')
const nueva = reactive({
  servicio: '',
  asistente: '',
  monto: '',
  moneda: 'PEN' as Moneda,
  vence: new Date().toLocaleDateString('en-CA', { timeZone: 'America/Lima' }),
})
const pendientes = computed(() => solicitudes.value.filter((s) => s.estado === 'pendiente').length)

async function guardar(valores: Record<string, unknown>) {
  limites.value = {
    por_pago: String(valores.por_pago || '') || null,
    mensual: String(valores.mensual || '') || null,
  }
}
function agregar() {
  if (!nueva.servicio || !nueva.monto) return
  solicitudes.value.unshift({
    id: crypto.randomUUID(),
    servicio: nueva.servicio,
    asistente: nueva.asistente || 'Tu asistente',
    monto: nueva.monto,
    moneda: nueva.moneda,
    estado: 'pendiente',
    fecha_vencimiento: nueva.vence,
    creado_en: new Date().toISOString(),
    motivo: null,
    resuelta_por: null,
    resuelta_en: null,
  })
  filtro.value = 'pendiente'
}
function resolver(id: string, estado: EstadoSolicitud, motivo: string | null = null) {
  const s = solicitudes.value.find((x) => x.id === id)
  if (s)
    Object.assign(s, { estado, motivo, resuelta_por: 'Tú', resuelta_en: new Date().toISOString() })
}
</script>

<template>
  <div class="revision">
    <header class="borde">
      <img
        src="/brand/deconsta/logo/deconsta-wordmark-white.svg"
        alt="Deconsta"
        width="132"
        height="26"
      />
      <span>Revisión de diseño</span>
    </header>
    <main class="hoja">
      <header class="encabezado">
        <h1>Límites y aprobaciones</h1>
        <p>Decide hasta cuánto puede pagar tu asistente sin pedirte permiso.</p>
      </header>
      <LimitesSuperficie
        :limites="limites"
        :consumo="consumo"
        :estado-pantalla="estadoLimites"
        :guardar="guardar"
        @reintentar="estadoLimites = 'lista'"
      />
      <div class="separador"></div>
      <SolicitudesSuperficie
        :solicitudes="solicitudes"
        :filtro="filtro"
        :pendientes="pendientes"
        :estado-pantalla="estadoSolicitudes"
        @filtrar="filtro = $event"
        @aprobar="resolver($event, 'aprobada')"
        @rechazar="(id, motivo) => resolver(id, 'rechazada', motivo)"
        @reintentar="estadoSolicitudes = 'lista'"
      />
    </main>
    <details class="controles">
      <summary>Controles de revisión</summary>
      <p>Esta ruta solo existe en desarrollo. Los datos se conectan en TASK-25.</p>
      <div class="grupo">
        <label
          >Límites
          <select v-model="estadoLimites">
            <option value="lista">Listos</option>
            <option value="cargando">Cargando</option>
            <option value="error">Error</option>
          </select></label
        >
        <label
          >Solicitudes
          <select v-model="estadoSolicitudes">
            <option value="lista">Listas</option>
            <option value="cargando">Cargando</option>
            <option value="error">Error</option>
          </select></label
        >
        <label>Validado (S/) <input v-model="consumo.validado" inputmode="decimal" /></label>
        <label>En proceso (S/) <input v-model="consumo.reservado" inputmode="decimal" /></label>
      </div>
      <form class="grupo" @submit.prevent="agregar">
        <label>Servicio <input v-model="nueva.servicio" /></label>
        <label>Asistente <input v-model="nueva.asistente" /></label>
        <label>Monto <input v-model="nueva.monto" inputmode="decimal" /></label>
        <label
          >Moneda
          <select v-model="nueva.moneda">
            <option>PEN</option>
            <option>USD</option>
          </select></label
        >
        <label>Vence <input v-model="nueva.vence" type="date" /></label>
        <button type="submit">Agregar solicitud</button>
      </form>
    </details>
  </div>
</template>

<style scoped>
.revision {
  min-height: 100svh;
  padding: 0 var(--margen-mesa) var(--margen-mesa);
  background: var(--deconsta-primary);
}
.borde {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-height: 72px;
  color: var(--deconsta-sobre-mesa);
  font-size: var(--texto-sm);
}
.borde img {
  display: block;
  width: 132px;
  height: auto;
}
.hoja {
  padding: clamp(24px, 4vw, 56px);
  border-radius: var(--radio-hoja);
  background: var(--deconsta-paper);
  color: var(--deconsta-ink);
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
.controles {
  margin-top: 16px;
  padding: 14px 18px;
  border-radius: var(--radio-control);
  background: var(--deconsta-paper);
  color: var(--deconsta-ink);
  font-size: var(--texto-sm);
}
.controles summary {
  font-weight: 700;
  cursor: pointer;
}
.grupo {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 10px 16px;
  margin-top: 12px;
}
.grupo label {
  display: grid;
  gap: 4px;
}
.grupo input,
.grupo select {
  min-height: 34px;
  padding: 0 8px;
}
</style>
