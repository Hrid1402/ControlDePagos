<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'
import {
  ESTADOS_SOLICITUD,
  fechaCorta,
  monto,
  venceHoy,
  type EstadoSolicitud,
  type Solicitud,
} from './modelo'

// H05 CA06 a CA10: solicitudes de aprobación que la asistente envía al superar un límite.
const props = withDefaults(
  defineProps<{
    solicitudes?: Solicitud[]
    filtro?: EstadoSolicitud
    pendientes?: number
    estadoPantalla?: 'lista' | 'cargando' | 'error'
    /** Solicitud con una respuesta en curso: sus botones esperan. */
    ocupada?: string | null
  }>(),
  {
    solicitudes: () => [],
    filtro: 'pendiente',
    pendientes: 0,
    estadoPantalla: 'lista',
    ocupada: null,
  },
)
const emit = defineEmits<{
  filtrar: [estado: EstadoSolicitud]
  aprobar: [id: string]
  rechazar: [id: string, motivo: string | null]
  reintentar: []
}>()

const rechazando = ref<string | null>(null)
const motivo = ref('')
const LARGO_MOTIVO = 300
const VACIOS: Record<EstadoSolicitud, string> = {
  pendiente: 'No tienes solicitudes por aprobar. Te avisaremos cuando llegue una.',
  aprobada: 'Todavía no aprobaste solicitudes.',
  rechazada: 'Todavía no rechazaste solicitudes.',
}
const visibles = computed(() => props.solicitudes.filter((s) => s.estado === props.filtro))

async function abrirRechazo(id: string) {
  rechazando.value = id
  motivo.value = ''
  await nextTick()
  document.getElementById(`motivo-${id}`)?.focus()
}
function confirmarRechazo(id: string) {
  emit('rechazar', id, motivo.value.trim() || null)
  rechazando.value = null
}
</script>

<template>
  <section class="solicitudes" aria-labelledby="solicitudes-titulo">
    <header class="cabecera">
      <h2 id="solicitudes-titulo">Solicitudes de aprobación</h2>
      <div class="filtros" role="group" aria-label="Mostrar solicitudes">
        <button
          v-for="opcion in ESTADOS_SOLICITUD"
          :key="opcion.valor"
          type="button"
          :aria-pressed="filtro === opcion.valor"
          @click="emit('filtrar', opcion.valor)"
        >
          {{ opcion.etiqueta }}
          <span v-if="opcion.valor === 'pendiente' && pendientes" class="contador">{{
            pendientes
          }}</span>
        </button>
      </div>
    </header>

    <div v-if="estadoPantalla === 'cargando'" aria-busy="true">
      <p class="lector" role="status">Cargando solicitudes…</p>
      <div v-for="n in 2" :key="n" class="marcador"></div>
    </div>

    <div v-else-if="estadoPantalla === 'error'" class="fallo" role="alert">
      <p>No pudimos cargar las solicitudes.</p>
      <Button label="Reintentar" icon="pi pi-refresh" text @click="emit('reintentar')" />
    </div>

    <p v-else-if="!visibles.length" class="vacio">{{ VACIOS[filtro] }}</p>

    <ul v-else class="lista">
      <li
        v-for="s in visibles"
        :key="s.id"
        class="solicitud"
        :class="[s.estado, { urgente: s.estado === 'pendiente' && venceHoy(s.fecha_vencimiento) }]"
      >
        <p class="monto">{{ monto(s.monto, s.moneda) }}</p>
        <div class="contexto">
          <p class="servicio">{{ s.servicio }}</p>
          <p class="dato">Pedida por {{ s.asistente }} el {{ fechaCorta(s.creado_en) }}.</p>
          <p v-if="s.estado === 'pendiente'" class="dato">
            <strong v-if="venceHoy(s.fecha_vencimiento)" class="hoy">Vence hoy</strong>
            <template v-else>Vence el {{ fechaCorta(s.fecha_vencimiento) }}</template>
            <template v-if="s.moneda === 'USD'"
              >. En dólares, siempre requiere tu aprobación</template
            >.
          </p>
          <p v-else-if="s.estado === 'aprobada'" class="dato resolucion">
            Aprobada<template v-if="s.resuelta_por"> por {{ s.resuelta_por }}</template
            ><template v-if="s.resuelta_en"> el {{ fechaCorta(s.resuelta_en) }}</template
            >. Solo autoriza este monto.
          </p>
          <p v-else class="dato resolucion">
            Rechazada<template v-if="s.resuelta_en"> el {{ fechaCorta(s.resuelta_en) }}</template
            >.<template v-if="s.motivo"> Motivo: {{ s.motivo }}</template>
          </p>
        </div>

        <div v-if="s.estado === 'pendiente'" class="acciones">
          <template v-if="rechazando !== s.id">
            <Button
              label="Aprobar"
              icon="pi pi-check"
              :loading="ocupada === s.id"
              :aria-label="`Aprobar ${monto(s.monto, s.moneda)} de ${s.servicio}`"
              @click="emit('aprobar', s.id)"
            />
            <Button
              label="Rechazar"
              severity="danger"
              text
              :disabled="ocupada === s.id"
              :aria-label="`Rechazar ${monto(s.monto, s.moneda)} de ${s.servicio}`"
              @click="abrirRechazo(s.id)"
            />
          </template>
          <form v-else class="rechazo" @submit.prevent="confirmarRechazo(s.id)">
            <label :for="`motivo-${s.id}`">Motivo para {{ s.asistente }} (opcional)</label>
            <Textarea
              :id="`motivo-${s.id}`"
              v-model="motivo"
              rows="2"
              auto-resize
              :maxlength="LARGO_MOTIVO"
            />
            <div class="botones">
              <Button type="submit" label="Rechazar solicitud" severity="danger" />
              <Button type="button" label="Cancelar" text @click="rechazando = null" />
            </div>
          </form>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.cabecera {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px 24px;
  margin-bottom: 20px;
}
h2 {
  margin: 0;
  font-size: var(--texto-lg);
  font-weight: 700;
  letter-spacing: -0.015em;
}
.filtros {
  display: flex;
  gap: 2px;
  padding: 3px;
  border-radius: var(--radio-control);
  background: var(--deconsta-realce);
}
.filtros button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 0 16px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--deconsta-ink);
  font-weight: 600;
  cursor: pointer;
}
.filtros button[aria-pressed='true'] {
  background: var(--deconsta-primary);
  color: var(--deconsta-paper);
}
.filtros button:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 2px;
}
.contador {
  min-width: 22px;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--deconsta-aviso);
  color: #fff;
  font-size: var(--texto-xs);
  text-align: center;
}
.lista {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}
/* Cada solicitud: el monto manda; contexto y acciones lo acompañan. */
.solicitud {
  display: grid;
  grid-template-columns: minmax(130px, auto) minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px 28px;
  padding: 18px 22px;
  border: 1px solid var(--deconsta-linea);
  border-radius: 5px 20px 5px 5px;
  background: var(--deconsta-paper-claro);
}
.solicitud.urgente {
  border-color: var(--deconsta-aviso);
  box-shadow: inset 4px 0 0 var(--deconsta-aviso);
}
.solicitud.aprobada,
.solicitud.rechazada {
  grid-template-columns: minmax(130px, auto) minmax(0, 1fr);
}
.monto {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: 1.5rem;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.rechazada .monto {
  color: var(--deconsta-muted);
  text-decoration: line-through;
  text-decoration-thickness: 1px;
}
.contexto p {
  margin: 0;
}
.servicio {
  font-weight: 700;
  overflow-wrap: anywhere;
}
.dato {
  margin-top: 2px !important;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  line-height: 1.5;
}
.hoy {
  color: var(--deconsta-aviso);
}
.acciones {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}
.acciones :deep(.p-button) {
  min-height: 42px;
}
.rechazo {
  display: grid;
  gap: 8px;
  width: min(340px, 100%);
}
.rechazo label {
  font-size: var(--texto-sm);
  font-weight: 600;
}
.botones {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.vacio {
  margin: 0;
  padding: 28px 0;
  color: var(--deconsta-muted);
}
.fallo {
  padding: 16px 20px;
  border-left: 3px solid var(--deconsta-error);
  background: var(--deconsta-error-fondo);
}
.fallo p {
  margin: 0 0 8px;
}
.marcador {
  height: 88px;
  margin-bottom: 12px;
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
}
@media (max-width: 760px) {
  .solicitud,
  .solicitud.aprobada,
  .solicitud.rechazada {
    grid-template-columns: minmax(0, 1fr);
    gap: 8px;
  }
  .acciones {
    justify-content: stretch;
  }
  .acciones :deep(.p-button) {
    flex: 1 1 auto;
  }
  .filtros {
    width: 100%;
  }
  .filtros button {
    flex: 1 1 auto;
    justify-content: center;
    gap: 6px;
    padding: 0 6px;
    font-size: var(--texto-sm);
  }
}
</style>
