<script setup lang="ts">
import { fechaHora, RESULTADOS_COMPROBANTE, type ComprobanteDeLaDeuda } from './detalle'
import { importe } from './modelo'

// H17 CA03: los comprobantes de la deuda con el resultado de su validación y, si no se validó, el
// motivo y la acción a seguir. Solo los validados cuentan como abono (CA09).
defineProps<{ comprobantes: ComprobanteDeLaDeuda[] }>()
const emit = defineEmits<{ abrir: [id: string] }>()
</script>

<template>
  <section class="comprobantes" aria-labelledby="comprobantes-titulo">
    <h2 id="comprobantes-titulo">Comprobantes</h2>
    <p v-if="!comprobantes.length" class="vacio">Aún no se adjunta ningún comprobante.</p>
    <ul v-else>
      <li
        v-for="c in comprobantes"
        :key="c.id"
        :class="`tono-${RESULTADOS_COMPROBANTE[c.estado].tono}`"
      >
        <span class="icono" aria-hidden="true">
          <i class="pi" :class="RESULTADOS_COMPROBANTE[c.estado].icono"></i>
        </span>
        <div class="cuerpo">
          <p class="titulo">
            <span class="resultado">{{ RESULTADOS_COMPROBANTE[c.estado].etiqueta }}</span>
            <span class="cifra">{{ importe(c.monto_aplicado, c.moneda) }}</span>
          </p>
          <p class="meta">
            {{ c.subido_por }} · {{ fechaHora(c.creado_en) }}
            <template v-if="c.reemplaza_a_id"> · reemplaza a uno rechazado</template>
          </p>
          <p v-if="c.observacion && c.estado !== 'validado'" class="observacion">
            {{ c.observacion }}
          </p>
        </div>
        <button
          type="button"
          class="ver"
          :aria-label="`Ver comprobante del ${fechaHora(c.creado_en)}`"
          @click="emit('abrir', c.id)"
        >
          Ver
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
h2 {
  margin: 0 0 12px;
  font-size: var(--texto-md);
}
.vacio {
  margin: 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
ul {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
li {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  align-items: start;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--deconsta-linea);
  border-radius: var(--radio-control);
  background: #fff;
}
.icono {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
}
.tono-exito .icono {
  background: #dff0e8;
  color: #135a42;
}
.tono-info .icono {
  background: #e6edf5;
  color: #34506e;
}
.tono-peligro .icono {
  background: var(--deconsta-error-fondo);
  color: var(--deconsta-error);
}
.tono-proceso .icono {
  background: #ebe8f5;
  color: #4a3d82;
}
p {
  margin: 0;
}
.titulo {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 4px 12px;
  font-weight: 700;
}
.cifra {
  font-variant-numeric: tabular-nums;
}
.tono-peligro .cifra {
  color: var(--deconsta-muted);
  text-decoration: line-through;
}
.meta {
  margin-top: 2px;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.observacion {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--deconsta-paper);
  font-size: var(--texto-sm);
  line-height: 1.5;
}
.tono-peligro .observacion {
  background: var(--deconsta-error-fondo);
  color: var(--deconsta-error);
}
.ver {
  min-height: 36px;
  padding: 0 6px;
  border: 0;
  background: none;
  color: var(--deconsta-primary);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}
.ver:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 2px;
}
</style>
