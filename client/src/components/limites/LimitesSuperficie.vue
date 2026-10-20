<script setup lang="ts">
import { computed } from 'vue'
import Button from 'primevue/button'
import FormularioBase from '@/components/formularios/FormularioBase.vue'
import CampoTexto from '@/components/formularios/CampoTexto.vue'
import { esquemaLimites, monto, type ConsumoMes, type Limites } from './modelo'

// H05 CA01 a CA05, CA11 y CA12: límites de la asistente activa y consumo del mes.
const props = withDefaults(
  defineProps<{
    limites?: Limites | null
    consumo?: ConsumoMes | null
    estadoPantalla?: 'lista' | 'cargando' | 'error'
    guardar: (valores: Record<string, unknown>) => Promise<unknown>
  }>(),
  { limites: null, consumo: null, estadoPantalla: 'lista' },
)
const emit = defineEmits<{ reintentar: [] }>()

const mensual = computed(() => (props.limites?.mensual ? Number(props.limites.mensual) : null))
const validado = computed(() => Number(props.consumo?.validado ?? 0))
const reservado = computed(() => Number(props.consumo?.reservado ?? 0))
const usado = computed(() => validado.value + reservado.value)
const proporcion = (valor: number) =>
  mensual.value ? `${Math.min(100, (valor / mensual.value) * 100)}%` : '0%'
const restante = computed(() => (mensual.value === null ? null : mensual.value - usado.value))
const excedido = computed(() => restante.value !== null && restante.value < 0)
const mesActual = new Date()
  .toLocaleDateString('es-PE', { timeZone: 'America/Lima', month: 'long' })
  .toLowerCase()
</script>

<template>
  <section class="limites" aria-labelledby="limites-titulo">
    <h2 id="limites-titulo" class="lector">Límites y consumo</h2>

    <div v-if="estadoPantalla === 'cargando'" class="rejilla" aria-busy="true">
      <p class="lector" role="status">Cargando límites…</p>
      <div class="marcador marcador--consumo"></div>
      <div class="marcador marcador--form"></div>
    </div>

    <div v-else-if="estadoPantalla === 'error'" class="fallo" role="alert">
      <p class="fallo-titulo">No pudimos cargar tus límites.</p>
      <p>No mostramos montos que no pudimos confirmar.</p>
      <Button label="Reintentar" icon="pi pi-refresh" @click="emit('reintentar')" />
    </div>

    <div v-else class="rejilla">
      <!-- CA04: el consumo es lo primero que se lee; el formulario lo acompaña. -->
      <article class="consumo" aria-labelledby="consumo-titulo">
        <h3 id="consumo-titulo">Consumo de {{ mesActual }}</h3>
        <p class="cifra">
          <span class="usado">{{ monto(usado) }}</span>
          <span v-if="mensual !== null" class="tope">de {{ monto(mensual) }}</span>
          <span v-else class="tope">sin límite mensual</span>
        </p>
        <div
          v-if="mensual !== null"
          class="barra"
          :class="{ excedida: excedido }"
          role="meter"
          aria-label="Consumo del límite mensual"
          :aria-valuenow="usado"
          aria-valuemin="0"
          :aria-valuemax="mensual"
          :aria-valuetext="`${monto(usado)} de ${monto(mensual)}`"
        >
          <span class="tramo validado" :style="{ width: proporcion(validado) }"></span>
          <span class="tramo reservado" :style="{ width: proporcion(reservado) }"></span>
        </div>
        <dl class="desglose">
          <div>
            <dt><span class="muestra validado" aria-hidden="true"></span>Pagado y validado</dt>
            <dd>{{ monto(validado) }}</dd>
          </div>
          <div>
            <dt><span class="muestra reservado" aria-hidden="true"></span>En proceso de pago</dt>
            <dd>{{ monto(reservado) }}</dd>
          </div>
          <div v-if="restante !== null">
            <dt>{{ excedido ? 'Sobre el límite' : 'Disponible' }}</dt>
            <dd :class="{ alerta: excedido }">{{ monto(Math.abs(restante)) }}</dd>
          </div>
        </dl>
        <p class="nota">Se reinicia el 1 de cada mes. Cambiar de asistente no lo reinicia.</p>
      </article>

      <div class="formulario">
        <FormularioBase
          :esquema="esquemaLimites"
          :valores-iniciales="{
            por_pago: limites?.por_pago ?? '',
            mensual: limites?.mensual ?? '',
          }"
          :guardar="guardar"
          texto-boton="Guardar límites"
          mensaje-exito="Tus límites se guardaron."
          descartable
        >
          <div class="campos">
            <CampoTexto
              nombre="por_pago"
              etiqueta="Límite por pago (S/)"
              inputmode="decimal"
              placeholder="Sin límite"
              ayuda="Un pago que lo supere te pedirá aprobación."
            />
            <CampoTexto
              nombre="mensual"
              etiqueta="Límite mensual (S/)"
              inputmode="decimal"
              placeholder="Sin límite"
              ayuda="Suma de lo que tu asistente paga en el mes."
            />
          </div>
          <ul class="reglas">
            <li>Deja un campo vacío para no poner ese límite.</li>
            <li>Aplica a tu asistente activa. Tus propios pagos no tienen límite.</li>
            <li>Un pago en dólares de tu asistente siempre te pide aprobación.</li>
            <li>Los cambios no afectan las solicitudes que ya te enviaron.</li>
          </ul>
        </FormularioBase>
      </div>
    </div>
  </section>
</template>

<style scoped>
.rejilla {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
  gap: clamp(24px, 4vw, 56px);
  align-items: start;
}
/* El consumo es una ficha de la marca: papel claro, franja verde y la esquina asimétrica. */
.consumo {
  padding: clamp(20px, 3vw, 32px);
  border-radius: 5px 32px 5px 5px;
  background: var(--deconsta-paper-claro);
  box-shadow: inset 4px 0 0 var(--deconsta-primary);
}
h3 {
  margin: 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  font-weight: 600;
}
.cifra {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 12px;
  margin: 10px 0 20px;
}
.usado {
  font-family: Literata, Georgia, serif;
  font-size: clamp(2rem, 1.6rem + 1.8vw, 2.875rem);
  font-weight: 500;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}
.tope {
  color: var(--deconsta-muted);
  font-size: var(--texto-md);
}
.barra {
  display: flex;
  height: 12px;
  overflow: hidden;
  border-radius: 6px;
  background: var(--deconsta-realce);
}
.tramo {
  height: 100%;
  transition: width 0.4s ease;
}
.validado {
  background: var(--deconsta-primary);
}
/* Lo reservado aún no es un abono: rayado, para no leerlo como pagado. */
.reservado {
  background: repeating-linear-gradient(135deg, var(--deconsta-primary) 0 4px, #7fb3a6 4px 8px);
}
.barra.excedida .validado {
  background: var(--deconsta-error);
}
.desglose {
  display: grid;
  gap: 10px;
  margin: 20px 0 0;
}
.desglose > div {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}
dt {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--deconsta-muted);
}
dd {
  margin: 0;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
dd.alerta {
  color: var(--deconsta-error);
}
.muestra {
  width: 12px;
  height: 12px;
  border-radius: 3px;
}
.nota {
  margin: 20px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.campos {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  align-items: start;
}
.reglas {
  display: grid;
  gap: 6px;
  margin: 0;
  padding-left: 18px;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  line-height: 1.5;
}
.fallo {
  max-width: 52ch;
  padding: 20px 24px;
  border-left: 3px solid var(--deconsta-error);
  background: var(--deconsta-error-fondo);
}
.fallo p {
  margin: 0 0 12px;
}
.fallo-titulo {
  font-weight: 700;
}
.marcador {
  border-radius: var(--radio-control);
  background: linear-gradient(90deg, #e6ece9 0%, #f4f7f5 50%, #e6ece9 100%) 0 0 / 200% 100%;
  animation: brillo 1.4s ease-in-out infinite;
}
.marcador--consumo {
  height: 260px;
}
.marcador--form {
  height: 220px;
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
@media (max-width: 900px) {
  .rejilla {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 520px) {
  .campos {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
