<script setup lang="ts">
import { computed } from 'vue'
import Dialog from 'primevue/dialog'
import FormularioBase from '@/components/formularios/FormularioBase.vue'
import CampoTexto from '@/components/formularios/CampoTexto.vue'
import CampoOpciones from '@/components/formularios/CampoOpciones.vue'
import CampoCasilla from '@/components/formularios/CampoCasilla.vue'
import { tintaSobre, type TipoCategoria } from '@/components/categorias/modelo'
import type { Servicio } from '@/components/servicios/modelo'
import CampoServicio from './CampoServicio.vue'
import CampoMonto from './CampoMonto.vue'
import CampoRecibo from './CampoRecibo.vue'
import CronogramaPrestamo from './CronogramaPrestamo.vue'
import {
  MONEDAS,
  VARIANTES,
  aDatos,
  cronograma,
  esquemaDeuda,
  estaVencida,
  fechaLarga,
  hoyEnLima,
  importe,
  nombrePeriodo,
  periodoDe,
  valoresIniciales,
  type DatosDeuda,
  type DeudaExistente,
} from './modelo'

// H11 CA01 a CA09: registrar la deuda del mes. El tipo de la categoría del servicio decide los
// campos (servicio variable, monto fijo, tarjeta o préstamo). Guardar lo resuelve quien lo usa
// (la API en TASK-41); si responde que ya existe, pasa la deuda existente en duplicada (CA03).
const props = withDefaults(
  defineProps<{
    servicios: Servicio[]
    guardar: (datos: DatosDeuda) => Promise<unknown>
    servicioInicial?: string
    duplicada?: DeudaExistente | null
    /** Día de Lima con el que se decide si ya venció (CA02). */
    hoy?: string
  }>(),
  { servicioInicial: '', duplicada: null, hoy: () => hoyEnLima() },
)
const emit = defineEmits<{ cerrar: []; verDuplicada: [id: string] }>()

const esquema = computed(() => esquemaDeuda(props.servicios))
const iniciales = computed(() => valoresIniciales(props.servicioInicial))
const opcionesMoneda = MONEDAS.map((m) => ({
  valor: m.valor,
  etiqueta: `${m.simbolo} ${m.etiqueta}`,
}))

const servicioDe = (id: unknown) => props.servicios.find((s) => s.id === id)
const tipoDe = (id: unknown) => servicioDe(id)?.categoria.tipo as TipoCategoria | undefined

async function guardar(valores: Record<string, unknown>) {
  const tipo = tipoDe(valores.servicio_id)
  if (!tipo) return
  await props.guardar(aDatos(valores, tipo))
}

const diaDe = (fecha: unknown) =>
  typeof fecha === 'string' && fecha ? Number(fecha.slice(8)) : null
function textoRepetir(valores: Record<string, unknown>) {
  const dia = diaDe(valores.fecha_vencimiento)
  const cuando = dia ? `cada día ${dia}` : 'el mismo día de cada mes'
  return tipoDe(valores.servicio_id) === 'monto_fijo'
    ? `Se crea sola ${cuando} por el mismo monto. Puedes cambiarla o detenerla cuando quieras.`
    : `Se crea sola ${cuando} esperando el recibo, sin monto, hasta que confirmes el importe.`
}
const periodoSugerido = (valores: Record<string, unknown>) =>
  typeof valores.fecha_vencimiento === 'string' && valores.fecha_vencimiento
    ? `Si lo dejas vacío, se usa ${nombrePeriodo(periodoDe(valores.fecha_vencimiento))}.`
    : 'Si lo dejas vacío, se usa el mes del vencimiento.'
</script>

<template>
  <Dialog
    visible
    modal
    header="Nueva deuda"
    :draggable="false"
    :style="{ width: 'min(720px, calc(100vw - 24px))' }"
    @update:visible="emit('cerrar')"
  >
    <FormularioBase
      :esquema="esquema"
      :valores-iniciales="iniciales"
      :guardar="guardar"
      texto-boton="Registrar deuda"
      mensaje-exito="La deuda se registró."
      limpiar-al-guardar
    >
      <template #default="{ valores }">
        <section class="bloque" aria-labelledby="deuda-servicio">
          <h3 id="deuda-servicio" class="lector">Servicio</h3>
          <CampoServicio :servicios="servicios" />
          <div
            v-if="servicioDe(valores.servicio_id)"
            class="variante"
            :data-tipo="tipoDe(valores.servicio_id)"
          >
            <span
              class="icono"
              aria-hidden="true"
              :style="{
                background: servicioDe(valores.servicio_id)!.categoria.color,
                color: tintaSobre(servicioDe(valores.servicio_id)!.categoria.color),
              }"
            >
              <i class="pi" :class="VARIANTES[tipoDe(valores.servicio_id)!].icono"></i>
            </span>
            <span>
              <strong>{{ VARIANTES[tipoDe(valores.servicio_id)!].titulo }}</strong>
              {{ VARIANTES[tipoDe(valores.servicio_id)!].explica }}
            </span>
          </div>
          <p v-else-if="!servicios.length" class="aviso">
            Todavía no tienes servicios activos. Registra uno en Servicios para cargarle deudas.
          </p>
        </section>

        <!-- Préstamo (CA07): el total, las cuotas y la primera fecha arman el cronograma. -->
        <template v-if="tipoDe(valores.servicio_id) === 'prestamo'">
          <section class="bloque" aria-labelledby="deuda-prestamo">
            <h3 id="deuda-prestamo">Préstamo</h3>
            <CampoOpciones nombre="moneda" etiqueta="Moneda" :opciones="opcionesMoneda" />
            <div class="trio">
              <CampoMonto
                nombre="monto_total"
                etiqueta="Total a pagar"
                :moneda="String(valores.moneda)"
                ayuda="Con intereses, como figura en tu contrato."
              />
              <CampoTexto
                nombre="cuotas_total"
                etiqueta="Número de cuotas"
                inputmode="numeric"
                autocomplete="off"
              />
              <CampoTexto nombre="fecha_primera_cuota" etiqueta="Primera cuota" tipo="date" />
            </div>
            <CronogramaPrestamo
              :cuotas="
                cronograma(valores.monto_total, valores.cuotas_total, valores.fecha_primera_cuota)
              "
              :moneda="valores.moneda === 'USD' ? 'USD' : 'PEN'"
            />
          </section>
        </template>

        <!-- Tarjeta (CA06): corte, fecha de pago, mínimo y total; se sugiere el total. -->
        <template v-else-if="tipoDe(valores.servicio_id) === 'tarjeta'">
          <section class="bloque" aria-labelledby="deuda-tarjeta">
            <h3 id="deuda-tarjeta">Estado de cuenta</h3>
            <div class="par">
              <CampoTexto nombre="fecha_corte" etiqueta="Fecha de corte" tipo="date" />
              <CampoTexto nombre="fecha_vencimiento" etiqueta="Fecha de pago" tipo="date" />
            </div>
            <CampoOpciones nombre="moneda" etiqueta="Moneda" :opciones="opcionesMoneda" />
            <div class="par">
              <CampoMonto
                nombre="pago_minimo"
                etiqueta="Pago mínimo (opcional)"
                :moneda="String(valores.moneda)"
              />
              <CampoMonto
                nombre="monto"
                etiqueta="Pago total"
                :moneda="String(valores.moneda)"
                destacado
              />
            </div>
            <p class="sugerencia">
              <i class="pi pi-lightbulb" aria-hidden="true"></i>
              Te sugerimos pagar el total: el mínimo deja saldo que genera intereses.
            </p>
          </section>
        </template>

        <!-- Servicio variable y monto fijo (CA01, CA09). -->
        <template v-else-if="tipoDe(valores.servicio_id)">
          <section class="bloque" aria-labelledby="deuda-importe">
            <h3 id="deuda-importe">Importe y fechas</h3>
            <div class="par">
              <CampoOpciones nombre="moneda" etiqueta="Moneda" :opciones="opcionesMoneda" />
              <CampoMonto
                nombre="monto"
                etiqueta="Monto"
                :moneda="String(valores.moneda)"
                destacado
              />
            </div>
            <div class="par">
              <CampoTexto nombre="fecha_vencimiento" etiqueta="Vencimiento" tipo="date" />
              <CampoTexto nombre="fecha_emision" etiqueta="Emisión (opcional)" tipo="date" />
            </div>
          </section>
        </template>

        <template v-if="tipoDe(valores.servicio_id) && tipoDe(valores.servicio_id) !== 'prestamo'">
          <!-- CA02: vencida se registra igual; solo se advierte. -->
          <p v-if="estaVencida(valores.fecha_vencimiento, hoy)" class="aviso" role="note">
            Esta deuda venció el {{ fechaLarga(String(valores.fecha_vencimiento)) }}. Puedes
            registrarla igual: aparecerá como vencida.
          </p>
          <!-- CA03: la API la rechaza si ya existe; aquí se muestra cuál es. -->
          <div v-if="duplicada" class="duplicada" role="alert">
            <p>
              <strong>Ya registraste la deuda de {{ nombrePeriodo(duplicada.periodo) }}.</strong>
              {{
                duplicada.monto ? importe(duplicada.monto, duplicada.moneda) : 'Espera su recibo'
              }}
              · vence el {{ fechaLarga(duplicada.fecha_vencimiento) }}. Cambia el periodo o edita
              esa deuda.
            </p>
            <button type="button" @click="emit('verDuplicada', duplicada.id)">Ver esa deuda</button>
          </div>

          <section class="bloque" aria-labelledby="deuda-recibo">
            <h3 id="deuda-recibo">Recibo</h3>
            <div class="par">
              <CampoTexto
                nombre="numero_recibo"
                etiqueta="Número de recibo (opcional)"
                autocomplete="off"
              />
              <CampoTexto
                nombre="periodo"
                etiqueta="Mes que cubre (opcional)"
                tipo="month"
                :ayuda="periodoSugerido(valores)"
              />
            </div>
            <CampoRecibo />
          </section>

          <!-- CA04 y CA05: dejarla programada para los meses siguientes. -->
          <CampoCasilla
            v-if="tipoDe(valores.servicio_id) !== 'tarjeta'"
            nombre="repetir"
            etiqueta="Registrar también los meses siguientes"
            :ayuda="textoRepetir(valores)"
          />
        </template>
      </template>
    </FormularioBase>
  </Dialog>
</template>

<style scoped>
.bloque {
  display: grid;
  gap: 16px;
}
.bloque + .bloque {
  padding-top: 20px;
  border-top: 1px solid var(--deconsta-linea);
}
h3 {
  margin: 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  font-weight: 700;
}
.par {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
}
.trio {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 16px;
  align-items: start;
}
/* La variante elegida se anuncia con el color de su categoría: se ve qué pide antes de llenar. */
.variante {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 4px 14px 4px 4px;
  background: var(--deconsta-paper-claro);
  font-size: var(--texto-sm);
  line-height: 1.5;
}
.variante strong {
  display: block;
  font-size: var(--texto-md);
}
.icono {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 4px 13px 4px 4px;
}
.sugerencia {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin: 0;
  color: var(--deconsta-primary);
  font-size: var(--texto-sm);
  font-weight: 600;
}
.sugerencia .pi {
  margin-top: 2px;
}
.aviso {
  margin: 0;
  padding: 12px 14px;
  border-left: 3px solid var(--deconsta-aviso);
  background: var(--deconsta-aviso-fondo);
  font-size: var(--texto-sm);
  line-height: 1.5;
}
.duplicada {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  padding: 12px 14px;
  border-left: 3px solid var(--deconsta-error);
  background: var(--deconsta-error-fondo);
  font-size: var(--texto-sm);
  line-height: 1.5;
}
.duplicada p {
  flex: 1 1 22rem;
  margin: 0;
}
.duplicada button {
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid var(--deconsta-error);
  border-radius: var(--radio-control);
  background: #fff;
  color: var(--deconsta-error);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.lector {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
@media (max-width: 560px) {
  .par,
  .trio {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
