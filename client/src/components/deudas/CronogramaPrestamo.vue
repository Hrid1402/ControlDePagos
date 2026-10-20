<script setup lang="ts">
import { computed, ref } from 'vue'
import { fechaLarga, importe, type Cuota, type Moneda } from './modelo'

// CA07: vista previa del cronograma mientras se escribe. La última cuota cuadra el total.
const props = defineProps<{ cuotas: Cuota[]; moneda: Moneda }>()
const VISIBLES = 6
const todas = ref(false)

const total = computed(() =>
  (props.cuotas.reduce((suma, c) => suma + Math.round(Number(c.monto) * 100), 0) / 100).toFixed(2),
)
const ajustada = computed(() => {
  const [primera] = props.cuotas
  const ultima = props.cuotas[props.cuotas.length - 1]
  return !!primera && !!ultima && props.cuotas.length > 1 && ultima.monto !== primera.monto
})
const mostradas = computed(() =>
  todas.value || props.cuotas.length <= VISIBLES + 1
    ? props.cuotas
    : [...props.cuotas.slice(0, VISIBLES), props.cuotas[props.cuotas.length - 1]!],
)
const ocultas = computed(() => props.cuotas.length - mostradas.value.length)
</script>

<template>
  <section class="cronograma" aria-labelledby="cronograma-titulo">
    <header>
      <h4 id="cronograma-titulo">Cronograma</h4>
      <p v-if="cuotas.length">
        {{ cuotas.length === 1 ? '1 cuota' : `${cuotas.length} cuotas` }} ·
        {{ importe(total, moneda) }}
      </p>
    </header>
    <p v-if="!cuotas.length" class="vacio">
      Escribe el total, el número de cuotas y la primera fecha para ver las cuotas.
    </p>
    <template v-else>
      <ol>
        <template v-for="(c, i) in mostradas" :key="c.numero">
          <li
            v-if="!todas && ocultas && i === mostradas.length - 1"
            class="salto"
            aria-hidden="true"
          >
            ⋯
          </li>
          <li>
            <span class="numero">{{ c.numero }}</span>
            <span class="fecha">{{ fechaLarga(c.fecha) }}</span>
            <span class="monto">{{ importe(c.monto, moneda) }}</span>
          </li>
        </template>
      </ol>
      <button v-if="ocultas" type="button" class="ver" @click="todas = true">
        Ver las {{ cuotas.length }} cuotas
      </button>
      <p v-if="ajustada" class="nota">
        La última cuota se ajusta en céntimos para que la suma sea exactamente el total.
      </p>
    </template>
  </section>
</template>

<style scoped>
.cronograma {
  padding: 16px 18px;
  border: 1px solid var(--deconsta-linea);
  border-radius: 5px 22px 5px 5px;
  background: var(--deconsta-paper-claro);
}
header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 4px 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--deconsta-ink);
}
h4 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-md);
  font-weight: 500;
}
header p {
  margin: 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  font-variant-numeric: tabular-nums;
}
ol {
  margin: 0;
  padding: 0;
  list-style: none;
}
li {
  display: grid;
  grid-template-columns: 2.5ch minmax(0, 1fr) auto;
  align-items: baseline;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--deconsta-linea);
  font-variant-numeric: tabular-nums;
}
li:last-child {
  border-bottom: 0;
}
.numero {
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  text-align: right;
}
.monto {
  font-weight: 600;
}
.salto {
  display: block;
  padding: 2px 0;
  color: var(--deconsta-muted);
  text-align: center;
}
.ver {
  margin-top: 6px;
  padding: 6px 0;
  border: 0;
  background: transparent;
  color: var(--deconsta-primary);
  font: inherit;
  font-size: var(--texto-sm);
  font-weight: 600;
  cursor: pointer;
}
.ver:hover {
  text-decoration: underline;
  text-underline-offset: 4px;
}
.vacio,
.nota {
  margin: 10px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
</style>
