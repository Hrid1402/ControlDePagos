<script setup lang="ts">
import { computed } from 'vue'
import Button from 'primevue/button'
import { tintaSobre } from '@/components/categorias/modelo'
import { fechaCorta } from '@/components/deudas/estados'
import { importe } from '@/components/deudas/modelo'
import { lugarDe, pasoDe, PASOS, textoTotal, type GrupoRuta, type ItemRuta } from './modelo'

// Un lugar de pago de la ruta (H23 CA01): sus deudas, lo que hay que llevar y, para cada una, lo
// que toca: elegirla, marcarla pagada al avanzar (CA03) o adjuntar su comprobante.
const props = defineProps<{
  grupo: GrupoRuta
  hoy: string
  seleccion: string[]
  ocupado?: string | null
}>()
const emit = defineEmits<{
  seleccionar: [ids: string[]]
  marcar: [id: string]
  adjuntar: [id: string]
  abrir: [id: string]
}>()

const lugar = computed(() => lugarDe(props.grupo.lugar))
const disponibles = computed(() => props.grupo.items.filter((i) => pasoDe(i) === 'disponible'))
const elegidas = computed(() => disponibles.value.filter((i) => props.seleccion.includes(i.id)))
const todas = computed(
  () => disponibles.value.length > 0 && elegidas.value.length === disponibles.value.length,
)
const nombre = (item: ItemRuta) => item.alias || item.empresa || 'Servicio'

function alternar(id: string, valor: boolean) {
  emit('seleccionar', valor ? [...props.seleccion, id] : props.seleccion.filter((s) => s !== id))
}
function alternarTodas(valor: boolean) {
  const ids = disponibles.value.map((i) => i.id)
  const sin = props.seleccion.filter((s) => !ids.includes(s))
  emit('seleccionar', valor ? [...sin, ...ids] : sin)
}
</script>

<template>
  <section class="grupo" :aria-labelledby="`lugar-${grupo.lugar ?? 'ninguno'}`">
    <header class="cabecera">
      <span class="lugar-icono" aria-hidden="true"><i class="pi" :class="lugar.icono"></i></span>
      <div class="lugar-texto">
        <h2 :id="`lugar-${grupo.lugar ?? 'ninguno'}`">{{ lugar.titulo }}</h2>
        <p>
          {{ grupo.items.length === 1 ? '1 deuda' : `${grupo.items.length} deudas` }} · llevar
          {{ textoTotal(grupo.items) }}
        </p>
      </div>
      <label v-if="disponibles.length > 1" class="todas">
        <input
          type="checkbox"
          :checked="todas"
          :aria-label="`Elegir todas las deudas de ${lugar.titulo}`"
          @change="alternarTodas(($event.target as HTMLInputElement).checked)"
        />
        Todas
      </label>
    </header>

    <ul class="filas">
      <li
        v-for="item in grupo.items"
        :key="item.id"
        class="fila"
        :class="[`paso-${pasoDe(item)}`, { elegida: seleccion.includes(item.id) }]"
      >
        <label v-if="pasoDe(item) === 'disponible'" class="casilla">
          <input
            type="checkbox"
            :checked="seleccion.includes(item.id)"
            :aria-label="`Agregar ${nombre(item)} a la ruta`"
            @change="alternar(item.id, ($event.target as HTMLInputElement).checked)"
          />
        </label>
        <span v-else class="casilla marca" aria-hidden="true">
          <i class="pi" :class="PASOS[pasoDe(item)]!.icono"></i>
        </span>

        <button type="button" class="nombre" @click="emit('abrir', item.id)">
          <span
            class="icono"
            aria-hidden="true"
            :style="{ background: item.categoria.color, color: tintaSobre(item.categoria.color) }"
          >
            <i class="pi" :class="item.categoria.icono"></i>
          </span>
          <span class="titulo">
            <strong>{{ nombre(item) }}</strong>
            <span class="sub">
              <template v-if="item.alias && item.empresa">{{ item.empresa }} · </template>
              <span class="codigo">{{ item.codigo_suministro }}</span>
              · vence {{ fechaCorta(item.fecha_vencimiento, hoy) }}
            </span>
            <span v-if="PASOS[pasoDe(item)]" class="paso">
              {{ PASOS[pasoDe(item)]!.texto }}
            </span>
          </span>
        </button>

        <span class="cifra">{{ importe(item.saldo, item.moneda) }}</span>

        <div class="accion">
          <Button
            v-if="pasoDe(item) === 'por_pagar'"
            label="Marcar pagada"
            icon="pi pi-check"
            size="small"
            :loading="ocupado === item.id"
            :aria-label="`Marcar pagada ${nombre(item)}`"
            @click="emit('marcar', item.id)"
          />
          <Button
            v-else-if="pasoDe(item) === 'declarada' || pasoDe(item) === 'rechazado'"
            label="Adjuntar comprobante"
            icon="pi pi-paperclip"
            size="small"
            outlined
            :loading="ocupado === item.id"
            :aria-label="`Adjuntar el comprobante de ${nombre(item)}`"
            @click="emit('adjuntar', item.id)"
          />
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.grupo {
  border: 1px solid var(--deconsta-linea);
  border-radius: 6px 18px 6px 6px;
  background: #fff;
  overflow: hidden;
}
.cabecera {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--deconsta-linea);
  background: var(--deconsta-paper-claro);
}
.lugar-icono {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 4px 13px 4px 4px;
  background: var(--deconsta-primary);
  color: var(--deconsta-paper);
}
.lugar-texto {
  flex: 1;
  min-width: 0;
}
h2 {
  margin: 0;
  font-size: var(--texto-md);
}
.lugar-texto p {
  margin: 2px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  font-variant-numeric: tabular-nums;
}
.todas {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: var(--texto-sm);
  font-weight: 700;
  cursor: pointer;
}
.filas {
  margin: 0;
  padding: 0;
  list-style: none;
}
.fila {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 10px 14px;
  padding: 12px 18px 12px 14px;
}
.fila + .fila {
  border-top: 1px solid var(--deconsta-realce);
}
.fila.elegida {
  background: var(--deconsta-realce);
}
.casilla {
  display: grid;
  place-items: center;
}
.casilla input,
.todas input {
  width: 20px;
  height: 20px;
  accent-color: var(--deconsta-primary);
  cursor: pointer;
}
.marca {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--deconsta-realce);
  color: var(--deconsta-primary);
  font-size: 0.75rem;
}
.paso-declarada .marca {
  background: var(--deconsta-primary);
  color: var(--deconsta-paper);
}
.paso-rechazado .marca {
  background: var(--deconsta-error);
  color: #fff;
}
.paso-espera_aprobacion .marca {
  background: var(--deconsta-aviso-fondo);
  color: var(--deconsta-aviso);
}
.nombre {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.nombre:hover strong {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.icono {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 4px 12px 4px 4px;
}
.titulo {
  display: grid;
  min-width: 0;
}
.titulo strong {
  overflow-wrap: anywhere;
}
.sub {
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.codigo {
  font-family: ui-monospace, 'SFMono-Regular', Menlo, monospace;
}
.paso {
  margin-top: 2px;
  color: var(--deconsta-primary);
  font-size: var(--texto-xs);
  font-weight: 800;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}
.paso-rechazado .paso {
  color: var(--deconsta-error);
}
.paso-espera_aprobacion .paso {
  color: var(--deconsta-aviso);
}
.paso-validando .paso {
  color: #34506e;
}
.cifra {
  font-family: Literata, Georgia, serif;
  font-size: 1.15rem;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.paso-declarada .cifra,
.paso-validando .cifra {
  color: var(--deconsta-muted);
  text-decoration: line-through;
  text-decoration-thickness: 1px;
}
/* Ancho fijo para que los montos queden en columna, tengan o no botón. */
.accion {
  display: flex;
  justify-content: flex-end;
  min-width: 196px;
}
button:focus-visible,
input:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 2px;
}
@media (max-width: 600px) {
  .cabecera {
    flex-wrap: wrap;
  }
  .fila {
    grid-template-columns: 24px minmax(0, 1fr) auto;
  }
  .accion {
    grid-column: 2 / -1;
    justify-content: flex-start;
    min-width: 0;
  }
  .accion:empty {
    display: none;
  }
  /* En celular el ícono de la categoría le quita espacio al nombre. */
  .icono {
    display: none;
  }
}
</style>
