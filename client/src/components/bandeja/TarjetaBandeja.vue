<script setup lang="ts">
import { computed } from 'vue'
import Button from 'primevue/button'
import { tintaSobre } from '@/components/categorias/modelo'
import { lugarEn } from '@/components/servicios/modelo'
import { fechaCorta } from '@/components/deudas/estados'
import { importe } from '@/components/deudas/modelo'
import { COMPROBANTES, motivo, type ItemBandeja, type Pestana } from './modelo'

// Una deuda de la bandeja (H15 CA05 a CA09, CA12): el motivo de su prioridad, lo que hay que pagar,
// dónde, y las acciones a la mano. Quien la usa ejecuta cada acción.
const props = defineProps<{
  item: ItemBandeja
  pestana: Pestana
  hoy: string
  seleccionada: boolean
  /** Id de la asistente en sesión, para decir «Tú» cuando ella está pagando. */
  usuarioId?: string
  ocupada?: boolean
}>()
const emit = defineEmits<{
  seleccionar: [valor: boolean]
  abrir: []
  ventanilla: []
  adjuntar: []
  fijar: [valor: boolean]
  posponer: []
}>()

const razon = computed(() => motivo(props.item))
const nombre = computed(() => props.item.alias || props.item.empresa || 'Servicio')
const monto = computed(() => props.item.saldo ?? props.item.monto)
const lugar = computed(() => lugarEn(props.item.lugar_pago))
const pagaOtro = computed(
  () => !!props.item.en_proceso && props.item.en_proceso.usuario_id !== props.usuarioId,
)
const seleccionable = computed(
  () => props.pestana === 'por_pagar' && !pagaOtro.value && props.item.monto !== null,
)
</script>

<template>
  <article class="tarjeta" :class="[`tono-${razon.tono}`, { seleccionada }]">
    <label v-if="seleccionable" class="casilla" :title="`Agregar ${nombre} a la ruta`">
      <input
        type="checkbox"
        :checked="seleccionada"
        :aria-label="`Agregar ${nombre} a la ruta de pagos`"
        @change="emit('seleccionar', ($event.target as HTMLInputElement).checked)"
      />
    </label>
    <span v-else class="casilla vacia" aria-hidden="true"></span>

    <div class="cuerpo">
      <div class="fila-superior">
        <span class="motivo">
          <i class="pi" :class="razon.icono" aria-hidden="true"></i>
          {{ razon.texto }}
        </span>
        <span v-if="item.fijada && item.etiqueta !== 'fijada'" class="fijada-marca">
          <i class="pi pi-thumbtack" aria-hidden="true"></i> Fijada
        </span>
      </div>

      <button type="button" class="nombre" @click="emit('abrir')">
        <span
          class="icono"
          aria-hidden="true"
          :style="{ background: item.categoria.color, color: tintaSobre(item.categoria.color) }"
        >
          <i class="pi" :class="item.categoria.icono"></i>
        </span>
        <span class="titulo">
          <strong>{{ nombre }}</strong>
          <span class="sub">
            <template v-if="item.alias && item.empresa">{{ item.empresa }} · </template>
            <span class="codigo">{{ item.codigo_suministro }}</span>
          </span>
        </span>
      </button>

      <p class="datos">
        <span
          ><i class="pi pi-calendar" aria-hidden="true"></i> Vence
          {{ fechaCorta(item.fecha_vencimiento, hoy) }}</span
        >
        <span v-if="lugar"><i class="pi pi-map-marker" aria-hidden="true"></i> {{ lugar }}</span>
      </p>

      <p v-if="item.en_proceso" class="proceso">
        <i class="pi pi-spinner" aria-hidden="true"></i>
        En proceso ·
        {{ item.en_proceso.usuario_id === usuarioId ? 'Tú' : item.en_proceso.nombre }}
        ({{ item.en_proceso.rol === 'gerente' ? 'gerente' : 'asistente' }})
      </p>
      <p
        v-if="item.comprobante_estado && COMPROBANTES[item.comprobante_estado]"
        class="comprobante"
        :class="{ rechazado: item.comprobante_estado === 'rechazado' }"
      >
        <i class="pi pi-file" aria-hidden="true"></i> {{ COMPROBANTES[item.comprobante_estado] }}
      </p>
    </div>

    <div class="monto">
      <template v-if="monto">
        <span class="cifra">{{ importe(monto, item.moneda) }}</span>
        <span v-if="item.saldo && item.monto && item.saldo !== item.monto" class="sub">
          de {{ importe(item.monto, item.moneda) }}
        </span>
      </template>
      <span v-else class="por-confirmar">Espera recibo</span>
    </div>

    <div class="acciones">
      <Button
        v-if="pestana === 'por_pagar' && !pagaOtro && item.monto !== null"
        label="Modo ventanilla"
        icon="pi pi-qrcode"
        size="small"
        :disabled="ocupada"
        @click="emit('ventanilla')"
      />
      <Button
        v-if="pestana !== 'por_validar' && !pagaOtro && item.monto !== null"
        label="Adjuntar comprobante"
        icon="pi pi-paperclip"
        size="small"
        :outlined="pestana === 'por_pagar'"
        :disabled="ocupada"
        @click="emit('adjuntar')"
      />
      <span class="secundarias">
        <button
          v-if="!item.orden_urgente"
          type="button"
          class="icono-boton texto"
          :aria-label="`Recordar ${nombre} mañana`"
          :disabled="ocupada"
          @click="emit('posponer')"
        >
          <i class="pi pi-moon" aria-hidden="true"></i> Mañana
        </button>
        <button
          type="button"
          class="icono-boton"
          :aria-pressed="item.fijada"
          :aria-label="item.fijada ? `Quitar ${nombre} de fijadas` : `Fijar ${nombre} arriba`"
          :title="item.fijada ? 'Quitar de fijadas' : 'Fijar arriba'"
          :disabled="ocupada"
          @click="emit('fijar', !item.fijada)"
        >
          <i class="pi pi-thumbtack" aria-hidden="true"></i>
        </button>
      </span>
    </div>
  </article>
</template>

<style scoped>
.tarjeta {
  --tono: var(--deconsta-linea);
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  gap: 12px 14px;
  padding: 16px 18px 16px 14px;
  border: 1px solid var(--deconsta-linea);
  border-left: 5px solid var(--tono);
  border-radius: 6px 18px 6px 6px;
  background: #fff;
  transition:
    box-shadow 120ms ease,
    border-color 120ms ease;
}
.tarjeta.seleccionada {
  border-color: var(--deconsta-primary);
  border-left-color: var(--tono);
  box-shadow: 0 0 0 2px rgb(7 90 80 / 0.18);
}
.tono-urgente {
  --tono: var(--deconsta-error);
  background: linear-gradient(90deg, #fdf3f4 0%, #fff 40%);
}
.tono-peligro {
  --tono: #c0475a;
}
.tono-fijada {
  --tono: var(--deconsta-primary);
}
.tono-aviso {
  --tono: #c98a12;
}
.tono-info {
  --tono: #4c6581;
}
.casilla {
  display: grid;
  place-items: start center;
  padding-top: 2px;
}
.casilla input {
  width: 20px;
  height: 20px;
  accent-color: var(--deconsta-primary);
  cursor: pointer;
}
.cuerpo {
  display: grid;
  gap: 8px;
  min-width: 0;
}
.fila-superior {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  align-items: center;
}
.motivo {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
  font-weight: 800;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}
.tono-urgente .motivo,
.tono-peligro .motivo {
  color: var(--deconsta-error);
}
.tono-fijada .motivo {
  color: var(--deconsta-primary);
}
.tono-aviso .motivo {
  color: var(--deconsta-aviso);
}
.fijada-marca {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--deconsta-realce);
  color: var(--deconsta-primary);
  font-size: var(--texto-xs);
  font-weight: 700;
}
.nombre {
  display: flex;
  align-items: center;
  gap: 12px;
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
  width: 38px;
  height: 38px;
  border-radius: 4px 13px 4px 4px;
}
.titulo {
  display: grid;
  min-width: 0;
}
.titulo strong {
  font-size: var(--texto-md);
  overflow-wrap: anywhere;
}
.sub {
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.codigo {
  font-family: ui-monospace, 'SFMono-Regular', Menlo, monospace;
}
.datos {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin: 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.datos .pi {
  margin-right: 4px;
  color: var(--deconsta-primary);
  font-size: 0.8rem;
}
.proceso,
.comprobante {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  color: #4a3d82;
  font-size: var(--texto-sm);
  font-weight: 700;
}
.comprobante {
  color: #34506e;
}
.comprobante.rechazado {
  color: var(--deconsta-error);
}
/* Fila propia a lo ancho de la tarjeta: las secundarias quedan siempre en el borde derecho,
   sin importar el ancho del monto. */
.acciones {
  display: flex;
  grid-column: 2 / -1;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.secundarias {
  display: inline-flex;
  gap: 4px;
  margin-left: auto;
}
.icono-boton {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 36px;
  min-height: 36px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: var(--radio-control);
  background: none;
  color: var(--deconsta-muted);
  font: inherit;
  font-size: var(--texto-sm);
  font-weight: 700;
  cursor: pointer;
}
.icono-boton:hover:not(:disabled) {
  border-color: var(--deconsta-linea);
  color: var(--deconsta-primary);
}
.icono-boton[aria-pressed='true'] {
  background: var(--deconsta-realce);
  color: var(--deconsta-primary);
}
.icono-boton:disabled {
  opacity: 0.5;
  cursor: wait;
}
button:focus-visible,
input:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 2px;
}
.monto {
  display: grid;
  align-content: start;
  justify-items: end;
  gap: 2px;
}
.cifra {
  font-family: Literata, Georgia, serif;
  font-size: 1.35rem;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.por-confirmar {
  color: #34506e;
  font-weight: 700;
}
@media (max-width: 600px) {
  .tarjeta {
    grid-template-columns: 24px minmax(0, 1fr);
  }
  .monto {
    grid-column: 2;
    grid-row: 1;
    justify-self: end;
    align-self: start;
  }
  .cuerpo {
    grid-column: 1 / -1;
    grid-row: 2;
  }
  .acciones {
    grid-column: 1 / -1;
    grid-row: 3;
  }
  .casilla {
    grid-row: 1;
  }
  .secundarias {
    margin-left: 0;
  }
}
</style>
