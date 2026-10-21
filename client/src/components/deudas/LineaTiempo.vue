<script setup lang="ts">
import { computed, ref } from 'vue'
import { importe, type Moneda } from './modelo'
import { fechaHora, textoEvento, type EventoDeuda } from './detalle'

// H17 CA04: qué pasó, quién lo hizo y cuándo, del más reciente al más antiguo. Se muestran los
// últimos MOSTRAR y el resto a pedido, para que una deuda con mucho movimiento no tape lo demás.
const props = defineProps<{ eventos: EventoDeuda[]; moneda: Moneda }>()
const MOSTRAR = 6
const todos = ref(false)
const visibles = computed(() => (todos.value ? props.eventos : props.eventos.slice(0, MOSTRAR)))

function complemento(evento: EventoDeuda): string {
  const d = evento.detalle
  if (typeof d.monto_anterior === 'string' && typeof d.monto_nuevo === 'string')
    return `${importe(d.monto_anterior, props.moneda)} → ${importe(d.monto_nuevo, props.moneda)}`
  if (typeof d.motivo === 'string' && d.motivo) return `«${d.motivo}»`
  return ''
}
/** El rol junto al nombre, salvo que el nombre ya lo diga. */
const rol = (nombre: string, r: string | null) =>
  (r === 'gerente' || r === 'asistente') && nombre.toLowerCase() !== r ? r : ''
</script>

<template>
  <section class="linea" aria-labelledby="linea-titulo">
    <h2 id="linea-titulo">Línea de tiempo</h2>
    <ol>
      <li
        v-for="(e, i) in visibles"
        :key="`${e.tipo}-${e.fecha}-${i}`"
        :class="{ sistema: !e.actor }"
      >
        <span class="marca" aria-hidden="true"></span>
        <p class="que">
          {{ textoEvento(e) }}
          <span v-if="complemento(e)" class="extra">{{ complemento(e) }}</span>
        </p>
        <p class="quien">
          <template v-if="e.actor"
            >{{ e.actor.nombre
            }}<template v-if="rol(e.actor.nombre, e.actor.rol)"
              >, {{ rol(e.actor.nombre, e.actor.rol) }}</template
            ></template
          >
          <template v-else>Automático</template>
          · <time :datetime="e.fecha">{{ fechaHora(e.fecha) }}</time>
        </p>
      </li>
    </ol>
    <button v-if="eventos.length > MOSTRAR" type="button" class="mas" @click="todos = !todos">
      {{ todos ? 'Ver menos' : `Ver los ${eventos.length - MOSTRAR} anteriores` }}
    </button>
  </section>
</template>

<style scoped>
h2 {
  margin: 0 0 14px;
  font-size: var(--texto-md);
}
ol {
  margin: 0;
  padding: 0;
  list-style: none;
}
li {
  position: relative;
  padding: 0 0 18px 26px;
}
li::before {
  position: absolute;
  top: 14px;
  bottom: 0;
  left: 5px;
  width: 2px;
  background: var(--deconsta-linea);
  content: '';
}
li:last-child::before {
  display: none;
}
.marca {
  position: absolute;
  top: 5px;
  left: 0;
  width: 12px;
  height: 12px;
  border: 2px solid var(--deconsta-primary);
  border-radius: 50%;
  background: var(--deconsta-paper);
}
li:first-child .marca {
  background: var(--deconsta-primary);
}
li.sistema .marca {
  border-color: #34506e;
  background: #e6edf5;
}
p {
  margin: 0;
}
.que {
  font-weight: 600;
  line-height: 1.4;
}
.extra {
  margin-left: 6px;
  color: var(--deconsta-muted);
  font-weight: 500;
}
.quien {
  margin-top: 2px;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.mas {
  min-height: 36px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--deconsta-primary);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}
.mas:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 2px;
}
</style>
