<script setup lang="ts">
import { computed, ref } from 'vue'
import { GRUPOS, accionDe, datosDe, dispositivo, fraseDe, hora, iniciales } from './modelo'
import type { RegistroHistorial } from './modelo'

const props = withDefaults(
  defineProps<{
    registro: RegistroHistorial
    /** Nombres de las cuentas del gerente por id, para nombrar a quién afectó la acción. */
    nombres?: Record<string, string>
    /** La hizo quien mira el historial: el monograma dice «Tú». */
    propio?: boolean
  }>(),
  { nombres: () => ({}), propio: false },
)

const abierto = ref(false)
const accion = computed(() => accionDe(props.registro.accion))
const frase = computed(() => fraseDe(props.registro, props.nombres))
const datos = computed(() => datosDe(props.registro.detalle))
const equipo = computed(() => dispositivo(props.registro.dispositivo))
const conDetalle = computed(() => datos.value.length > 0 || !!equipo.value || !!props.registro.ip)
const panel = computed(() => `registro-${props.registro.id}`)
</script>

<template>
  <li class="registro" :class="{ alerta: accion.alerta, abierto }">
    <time class="hora" :datetime="registro.creado_en">{{ hora(registro.creado_en) }}</time>
    <span class="monograma" :class="{ propio }" aria-hidden="true">{{
      propio ? 'Tú' : iniciales(registro.usuario_nombre)
    }}</span>
    <div class="cuerpo">
      <p class="frase">
        <strong>{{ registro.usuario_nombre }}</strong> {{ frase }}
      </p>
      <p class="meta">
        <span class="grupo">{{ GRUPOS[accion.grupo] }}</span>
        <span v-if="equipo" class="equipo">{{ equipo }}</span>
      </p>
      <div v-if="abierto" :id="panel" class="detalle">
        <dl>
          <div v-for="dato in datos" :key="dato.campo">
            <dt>{{ dato.campo }}</dt>
            <dd>{{ dato.valor }}</dd>
          </div>
          <div v-if="registro.dispositivo">
            <dt>Dispositivo</dt>
            <dd class="agente">{{ registro.dispositivo }}</dd>
          </div>
          <div v-if="registro.ip">
            <dt>IP</dt>
            <dd>{{ registro.ip }}</dd>
          </div>
        </dl>
      </div>
    </div>
    <button
      v-if="conDetalle"
      type="button"
      class="alternar"
      :aria-expanded="abierto"
      :aria-controls="panel"
      @click="abierto = !abierto"
    >
      {{ abierto ? 'Ocultar' : 'Ver detalle' }}
      <span class="lector">: {{ registro.usuario_nombre }} {{ frase }}</span>
    </button>
  </li>
</template>

<style scoped>
.registro {
  display: grid;
  grid-template-columns: 52px 36px minmax(0, 1fr) auto;
  align-items: start;
  gap: 4px 14px;
  padding: 14px 16px 14px 12px;
}
.registro + .registro {
  border-top: 1px solid var(--deconsta-linea);
}
.registro.abierto {
  border-radius: 4px 14px 4px 4px;
  background: var(--deconsta-paper-claro);
}
/* Un ingreso fallido o una cuenta eliminada se distinguen con franja y rótulo, no solo color. */
.registro.alerta {
  box-shadow: inset 3px 0 0 var(--deconsta-error);
}
.hora {
  padding-top: 7px;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  font-variant-numeric: tabular-nums;
}
.monograma {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 4px 12px 4px 4px;
  background: var(--deconsta-realce);
  color: var(--deconsta-primary);
  font-family: Literata, Georgia, serif;
  font-size: 0.875rem;
  font-weight: 600;
}
.monograma.propio {
  background: var(--deconsta-primary);
  color: var(--deconsta-paper);
  font-family: inherit;
  font-size: var(--texto-xs);
  font-weight: 700;
}
.alerta .monograma {
  background: var(--deconsta-error-fondo);
  color: var(--deconsta-error);
}
.cuerpo {
  min-width: 0;
}
.frase {
  margin: 0;
  padding-top: 5px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.frase strong {
  font-weight: 700;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  margin: 4px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.grupo {
  font-weight: 600;
}
.alerta .grupo {
  color: var(--deconsta-error);
}
.equipo::before {
  content: '';
  display: inline-block;
  width: 4px;
  height: 4px;
  margin: 0 10px 2px 0;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.5;
}
/* Enlace discreto: con decenas de filas, un botón con borde en cada una sería ruido. */
.alternar {
  min-height: 36px;
  padding: 0 4px;
  border: 0;
  border-radius: 2px;
  background: transparent;
  color: var(--deconsta-primary);
  font: inherit;
  font-size: var(--texto-sm);
  font-weight: 600;
  text-decoration: underline;
  text-decoration-color: transparent;
  text-underline-offset: 4px;
  cursor: pointer;
}
.alternar:hover,
.abierto .alternar {
  text-decoration-color: currentColor;
}
.alternar:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 2px;
}
.detalle {
  margin-top: 12px;
}
dl {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 12px 14px;
  border-left: 2px solid var(--deconsta-primary);
  background: var(--deconsta-paper);
}
dl div {
  display: grid;
  grid-template-columns: minmax(110px, 0.35fr) minmax(0, 1fr);
  gap: 12px;
}
dt {
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
dd {
  margin: 0;
  font-size: var(--texto-sm);
  font-weight: 600;
  overflow-wrap: anywhere;
}
dd.agente {
  font-weight: 400;
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
  .registro {
    grid-template-columns: 36px minmax(0, 1fr);
    padding: 14px 4px 14px 10px;
  }
  .hora {
    grid-column: 2;
    grid-row: 1;
    padding-top: 0;
  }
  .monograma {
    grid-row: 1 / span 2;
  }
  .cuerpo {
    grid-column: 2;
  }
  .alternar {
    grid-column: 2;
    justify-self: start;
    min-height: 32px;
    padding: 0;
  }
  dl div {
    grid-template-columns: minmax(0, 1fr);
    gap: 2px;
  }
}
</style>
