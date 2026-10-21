<script setup lang="ts">
import { computed, ref } from 'vue'
import Button from 'primevue/button'
import { tintaSobre } from '@/components/categorias/modelo'
import { lugarEn } from '@/components/servicios/modelo'
import EtiquetaDeuda from './EtiquetaDeuda.vue'
import ComprobantesDeuda from './ComprobantesDeuda.vue'
import LineaTiempo from './LineaTiempo.vue'
import ComentariosDeuda from './ComentariosDeuda.vue'
import { estadoDe, plazo } from './estados'
import { fechaHora, type AccionDeuda, type ComentarioDeuda, type DetalleDeuda } from './detalle'
import { fechaLarga, importe, nombrePeriodo } from './modelo'

// H17: toda la información de una deuda en un solo lugar para actuar sobre ella. Las acciones son
// las que manda el backend (CA07); una deuda anulada no tiene ninguna (CA08). Quien la usa trae los
// datos y ejecuta cada acción (TASK-55).
const props = withDefaults(
  defineProps<{
    detalle?: DetalleDeuda | null
    comentarios?: ComentarioDeuda[]
    estadoPantalla?: 'lista' | 'cargando' | 'error' | 'no_encontrada'
    hoy: string
    enviandoComentario?: boolean
    errorComentario?: string | null
    /** Acción en curso, para mostrar su botón cargando. */
    ocupado?: AccionDeuda | null
    /** El gerente valida los vouchers por confirmar o en revisión (TASK-109). */
    puedeValidar?: boolean
    /** Voucher con una decisión en curso. */
    validando?: string | null
  }>(),
  {
    detalle: null,
    comentarios: () => [],
    estadoPantalla: 'lista',
    enviandoComentario: false,
    errorComentario: null,
    ocupado: null,
    puedeValidar: false,
    validando: null,
  },
)
const emit = defineEmits<{
  volver: []
  accion: [accion: AccionDeuda]
  comentar: [texto: string]
  abrirComprobante: [id: string]
  validarComprobante: [id: string]
  rechazarComprobante: [id: string]
  reintentar: []
}>()

const comentariosRef = ref<InstanceType<typeof ComentariosDeuda> | null>(null)
defineExpose({ limpiarComentario: () => comentariosRef.value?.limpiar() })

const d = computed(() => props.detalle)
const nombre = computed(() => (d.value ? d.value.servicio.alias || d.value.servicio.empresa : ''))
const puede = (accion: AccionDeuda) => !!d.value?.acciones.includes(accion)
const cerrada = computed(() => d.value?.estado === 'pagada' || d.value?.estado === 'anulada')
const avance = computed(() => {
  const monto = Number(d.value?.monto ?? 0)
  return monto > 0 ? Math.min(100, (Number(d.value!.pagado) / monto) * 100) : 0
})
const plazoDeuda = computed(() =>
  d.value ? plazo(d.value.fecha_vencimiento, props.hoy, cerrada.value) : null,
)

const copiado = ref(false)
async function copiarCodigo() {
  if (!d.value) return
  try {
    await navigator.clipboard.writeText(d.value.servicio.codigo_suministro)
    copiado.value = true
    setTimeout(() => (copiado.value = false), 2000)
  } catch {
    copiado.value = false
  }
}

/** Filas de «Datos» que tienen valor (CA01). */
const datos = computed(() => {
  const x = d.value
  if (!x) return []
  const filas: [string, string][] = [
    ['Categoría', x.categoria.nombre],
    ['Periodo', nombrePeriodo(x.periodo)],
    ['Vencimiento', fechaLarga(x.fecha_vencimiento)],
  ]
  if (x.fecha_emision) filas.push(['Emisión', fechaLarga(x.fecha_emision)])
  if (x.fecha_estimada && x.monto === null)
    filas.push(['Recibo esperado', fechaLarga(x.fecha_estimada)])
  if (x.fecha_corte) filas.push(['Corte', fechaLarga(x.fecha_corte)])
  if (x.pago_minimo) filas.push(['Pago mínimo', importe(x.pago_minimo, x.moneda)])
  if (x.cuota_numero && x.cuotas_total)
    filas.push(['Cuota', `${x.cuota_numero} de ${x.cuotas_total}`])
  if (x.numero_recibo) filas.push(['N.º de recibo', x.numero_recibo])
  const lugar = lugarEn(x.servicio.lugar_pago)
  if (lugar) filas.push(['Se paga en', lugar])
  if (x.servicio.titular) filas.push(['Titular', x.servicio.titular])
  return filas
})
</script>

<template>
  <div class="detalle">
    <button type="button" class="volver" @click="emit('volver')">
      <i class="pi pi-arrow-left" aria-hidden="true"></i> Volver a deudas
    </button>

    <div v-if="estadoPantalla === 'cargando'" aria-busy="true">
      <p class="lector" role="status">Cargando la deuda…</p>
      <div class="marcador alto"></div>
      <div class="marcador"></div>
      <div class="marcador"></div>
    </div>

    <div v-else-if="estadoPantalla === 'error'" class="fallo" role="alert">
      <h2>No pudimos cargar la deuda.</h2>
      <p>Revisa tu conexión e inténtalo otra vez.</p>
      <Button label="Reintentar" icon="pi pi-refresh" @click="emit('reintentar')" />
    </div>

    <div v-else-if="estadoPantalla === 'no_encontrada' || !d" class="fallo neutro" role="alert">
      <h2>Esta deuda no existe o ya no tienes acceso.</h2>
      <p>Puede que el enlace sea antiguo. Vuelve a la lista para buscarla.</p>
      <Button label="Ir a deudas" outlined @click="emit('volver')" />
    </div>

    <template v-else>
      <header class="cabecera">
        <span
          class="icono"
          aria-hidden="true"
          :style="{ background: d.categoria.color, color: tintaSobre(d.categoria.color) }"
        >
          <i class="pi" :class="d.categoria.icono"></i>
        </span>
        <div class="titulos">
          <h1>{{ nombre }}</h1>
          <p class="sub">
            <template v-if="d.servicio.alias">{{ d.servicio.empresa }} · </template>
            Código
            <span class="codigo">{{ d.servicio.codigo_suministro }}</span>
            <button
              type="button"
              class="copiar"
              :aria-label="copiado ? 'Código copiado' : 'Copiar el código de suministro'"
              @click="copiarCodigo"
            >
              <i class="pi" :class="copiado ? 'pi-check' : 'pi-copy'" aria-hidden="true"></i>
              {{ copiado ? 'Copiado' : 'Copiar' }}
            </button>
          </p>
        </div>
        <EtiquetaDeuda :estado="d.estado" class="estado" />
      </header>

      <p v-if="d.estado === 'anulada'" class="aviso neutro">
        <i class="pi pi-ban" aria-hidden="true"></i>
        Esta deuda está anulada: ya no se cobra y se conserva solo como historial.
      </p>
      <p v-else-if="d.orden_urgente" class="aviso urgente">
        <i class="pi pi-bolt" aria-hidden="true"></i>
        Hay una orden urgente del gerente
        <template v-if="d.orden_urgente.plazo">
          para pagarla antes de las {{ fechaHora(d.orden_urgente.plazo) }}</template
        >.
      </p>
      <p v-if="d.en_proceso" class="aviso proceso">
        <i class="pi pi-spinner" aria-hidden="true"></i>
        {{ d.en_proceso.nombre }} ({{ d.en_proceso.rol === 'gerente' ? 'gerente' : 'asistente' }})
        está pagándola<template v-if="d.en_proceso.desde">
          desde el {{ fechaHora(d.en_proceso.desde) }}</template
        >.
      </p>

      <div class="rejilla">
        <div class="principal">
          <section
            class="importe orden-1"
            :class="{ apagado: d.estado === 'anulada' }"
            aria-label="Importe"
          >
            <template v-if="d.monto !== null">
              <p class="etiqueta-cifra">
                {{ d.estado === 'pagada' ? 'Pagado' : 'Saldo por pagar' }}
              </p>
              <p class="cifra">
                {{ importe(d.estado === 'pagada' ? d.monto : (d.saldo ?? d.monto), d.moneda) }}
              </p>
              <div
                v-if="Number(d.pagado) > 0"
                class="avance"
                role="meter"
                :aria-valuenow="Math.round(avance)"
                aria-valuemin="0"
                aria-valuemax="100"
                :aria-label="`Pagado ${Math.round(avance)} %`"
              >
                <span :style="{ width: `${avance}%` }"></span>
              </div>
              <p class="desglose">
                Monto {{ importe(d.monto, d.moneda) }}
                <template v-if="Number(d.pagado) > 0">
                  · Abonado {{ importe(d.pagado, d.moneda) }}</template
                >
                <template v-if="d.pago_total && d.pago_minimo">
                  · Mínimo {{ importe(d.pago_minimo, d.moneda) }}</template
                >
              </p>
            </template>
            <template v-else>
              <p class="etiqueta-cifra">Monto por confirmar</p>
              <p class="cifra por-confirmar">
                {{
                  d.monto_proyectado
                    ? `≈ ${importe(d.monto_proyectado, d.moneda)}`
                    : 'Sin estimación'
                }}
              </p>
              <p class="desglose">
                {{ estadoDe(d.estado).explica }}
                <template v-if="d.monto_proyectado">
                  El estimado es el monto del mes anterior.</template
                >
              </p>
            </template>
            <p v-if="plazoDeuda?.texto" class="plazo" :class="`plazo-${plazoDeuda.tono}`">
              <i class="pi pi-calendar" aria-hidden="true"></i>
              {{ plazoDeuda.texto }} · {{ fechaLarga(d.fecha_vencimiento) }}
            </p>
          </section>

          <div v-if="d.acciones.some((a) => a !== 'comentar')" class="acciones orden-2">
            <Button
              v-if="puede('iniciar_pago')"
              label="Pagar en ventanilla"
              icon="pi pi-qrcode"
              :loading="ocupado === 'iniciar_pago'"
              @click="emit('accion', 'iniciar_pago')"
            />
            <Button
              v-if="puede('adjuntar_comprobante')"
              label="Adjuntar comprobante"
              icon="pi pi-paperclip"
              :outlined="puede('iniciar_pago')"
              :loading="ocupado === 'adjuntar_comprobante'"
              @click="emit('accion', 'adjuntar_comprobante')"
            />
            <Button
              v-if="puede('ordenar_urgente')"
              label="Ordenar pago urgente"
              icon="pi pi-bolt"
              outlined
              @click="emit('accion', 'ordenar_urgente')"
            />
            <Button
              v-if="puede('editar')"
              label="Editar"
              icon="pi pi-pencil"
              text
              @click="emit('accion', 'editar')"
            />
            <Button
              v-if="puede('cancelar_inicio')"
              label="Cancelar el pago en curso"
              text
              :loading="ocupado === 'cancelar_inicio'"
              @click="emit('accion', 'cancelar_inicio')"
            />
            <Button
              v-if="puede('anular')"
              label="Anular"
              icon="pi pi-ban"
              text
              severity="danger"
              @click="emit('accion', 'anular')"
            />
          </div>

          <ComprobantesDeuda
            :comprobantes="d.comprobantes"
            :puede-validar="puedeValidar"
            :ocupado="validando"
            class="bloque orden-4"
            @abrir="emit('abrirComprobante', $event)"
            @validar="emit('validarComprobante', $event)"
            @rechazar="emit('rechazarComprobante', $event)"
          />
          <LineaTiempo :eventos="d.linea_tiempo" :moneda="d.moneda" class="bloque orden-7" />
        </div>

        <aside class="lateral">
          <section class="tarjeta orden-3" aria-labelledby="datos-titulo">
            <h2 id="datos-titulo">Datos</h2>
            <dl class="datos">
              <div v-for="[clave, valor] in datos" :key="clave">
                <dt>{{ clave }}</dt>
                <dd>{{ valor }}</dd>
              </div>
            </dl>
            <div v-if="d.recibo_enlace" class="recibo">
              <a :href="d.recibo_enlace" target="_blank" rel="noopener">
                <i class="pi pi-file" aria-hidden="true"></i> Ver recibo
              </a>
              <a :href="d.recibo_enlace" download>
                <i class="pi pi-download" aria-hidden="true"></i> Descargar
              </a>
            </div>
            <p v-if="d.servicio.notas" class="notas">
              <i class="pi pi-info-circle" aria-hidden="true"></i> {{ d.servicio.notas }}
            </p>
          </section>

          <section
            v-if="d.historial_montos.length"
            class="tarjeta orden-6"
            aria-labelledby="montos-titulo"
          >
            <h2 id="montos-titulo">Cambios de monto</h2>
            <ul class="montos">
              <li v-for="(c, i) in d.historial_montos" :key="i">
                <span class="de-a">
                  <s>{{ importe(c.monto_anterior, d.moneda) }}</s>
                  <i class="pi pi-arrow-right" aria-hidden="true"></i>
                  <strong>{{ importe(c.monto_nuevo, d.moneda) }}</strong>
                </span>
                <span class="meta"
                  >{{ c.usuario ?? 'Automático' }} · {{ fechaHora(c.creado_en) }}</span
                >
              </li>
            </ul>
          </section>

          <ComentariosDeuda
            ref="comentariosRef"
            class="tarjeta orden-5"
            :comentarios="comentarios"
            :puede-comentar="puede('comentar')"
            :enviando="enviandoComentario"
            :error="errorComentario"
            @comentar="emit('comentar', $event)"
          />
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.detalle {
  max-width: 1120px;
}
.volver {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  margin-bottom: 16px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--deconsta-primary);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}
button:focus-visible,
a:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 2px;
}
.cabecera {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}
.icono {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  border-radius: 4px 18px 4px 4px;
  font-size: 1.3rem;
}
h1 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: clamp(1.75rem, 1.4rem + 1.2vw, 2.4rem);
  font-weight: 500;
  letter-spacing: -0.02em;
  line-height: 1.15;
  overflow-wrap: anywhere;
}
.sub {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  margin: 6px 0 0;
  color: var(--deconsta-muted);
}
.codigo {
  color: var(--deconsta-ink);
  font-family: ui-monospace, 'SFMono-Regular', Menlo, monospace;
  font-weight: 600;
  letter-spacing: 0.03em;
}
.copiar {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--deconsta-linea);
  border-radius: 999px;
  background: var(--deconsta-paper-claro);
  color: var(--deconsta-primary);
  font: inherit;
  font-size: var(--texto-xs);
  font-weight: 700;
  cursor: pointer;
}
.aviso {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin: 0 0 12px;
  padding: 12px 16px;
  border-left: 3px solid;
  border-radius: 0 var(--radio-control) var(--radio-control) 0;
  line-height: 1.5;
}
.aviso .pi {
  margin-top: 3px;
}
.aviso.neutro {
  border-color: var(--deconsta-muted);
  background: var(--deconsta-realce);
}
.aviso.urgente {
  border-color: var(--deconsta-error);
  background: var(--deconsta-error-fondo);
  color: var(--deconsta-error);
  font-weight: 600;
}
.aviso.proceso {
  border-color: #4a3d82;
  background: #ebe8f5;
  color: #4a3d82;
}
.rejilla {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
  align-items: start;
  gap: clamp(20px, 3vw, 36px);
  margin-top: 8px;
}
.principal {
  display: grid;
  gap: 20px;
}
.importe {
  padding: 22px 24px;
  border-radius: 4px 26px 4px 4px;
  background: var(--deconsta-ink);
  color: var(--deconsta-paper);
}
.importe p {
  margin: 0;
}
/* Anulada: el importe ya no se cobra y deja de ser lo principal. */
.importe.apagado {
  background: var(--deconsta-realce);
  color: var(--deconsta-muted);
}
.importe.apagado .etiqueta-cifra,
.importe.apagado .desglose {
  color: var(--deconsta-muted);
}
.importe.apagado .cifra {
  text-decoration: line-through;
}
.etiqueta-cifra {
  color: var(--deconsta-sobre-mesa);
  font-size: var(--texto-sm);
  font-weight: 600;
}
.cifra {
  margin-top: 4px !important;
  font-family: Literata, Georgia, serif;
  font-size: clamp(2.1rem, 1.6rem + 2vw, 3rem);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1.1;
}
.cifra.por-confirmar {
  font-size: clamp(1.6rem, 1.3rem + 1.4vw, 2.2rem);
}
.avance {
  height: 6px;
  margin: 14px 0 10px;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(255 255 255 / 0.16);
}
.avance span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #8fd5bc;
}
.desglose {
  margin-top: 8px !important;
  color: var(--deconsta-sobre-mesa);
  font-size: var(--texto-sm);
  line-height: 1.5;
}
.plazo {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px !important;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgb(255 255 255 / 0.1);
  font-size: var(--texto-sm);
  font-weight: 700;
}
.plazo-peligro {
  background: #f6d5d9;
  color: var(--deconsta-error);
}
.plazo-aviso {
  background: var(--deconsta-aviso-fondo);
  color: var(--deconsta-aviso);
}
.acciones {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.acciones :deep(.p-button) {
  min-height: 44px;
}
.bloque {
  padding-top: 20px;
  border-top: 1px solid var(--deconsta-linea);
}
.lateral {
  display: grid;
  gap: 16px;
}
.tarjeta {
  padding: 18px 20px;
  border: 1px solid var(--deconsta-linea);
  border-radius: var(--radio-control);
  background: var(--deconsta-paper-claro);
}
.tarjeta h2 {
  margin: 0 0 12px;
  font-size: var(--texto-md);
}
.datos {
  display: grid;
  gap: 10px;
  margin: 0;
}
.datos div {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  font-size: var(--texto-sm);
}
.datos dt {
  color: var(--deconsta-muted);
}
.datos dd {
  margin: 0;
  font-weight: 600;
  text-align: right;
}
.datos dd::first-letter {
  text-transform: uppercase;
}
.recibo {
  display: flex;
  gap: 16px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--deconsta-linea);
}
.recibo a {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--deconsta-primary);
  font-size: var(--texto-sm);
  font-weight: 700;
  text-decoration: none;
}
.recibo a:hover {
  text-decoration: underline;
}
.notas {
  display: flex;
  gap: 8px;
  margin: 12px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  line-height: 1.5;
}
.montos {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.montos li {
  display: grid;
  gap: 2px;
}
.de-a {
  display: flex;
  align-items: center;
  gap: 8px;
  font-variant-numeric: tabular-nums;
}
.de-a s {
  color: var(--deconsta-muted);
}
.de-a .pi {
  color: var(--deconsta-muted);
  font-size: 0.7rem;
}
.meta {
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
}
.fallo {
  max-width: 52ch;
  padding: 24px 28px;
  border-left: 3px solid var(--deconsta-error);
  background: var(--deconsta-error-fondo);
}
.fallo.neutro {
  border-color: var(--deconsta-muted);
  background: var(--deconsta-realce);
}
.fallo h2 {
  margin: 0;
  font-size: var(--texto-lg);
}
.fallo p {
  margin: 8px 0 20px;
}
.marcador {
  height: 120px;
  margin-bottom: 12px;
  border-radius: var(--radio-control);
  background: linear-gradient(90deg, #e6ece9 0%, #f4f7f5 50%, #e6ece9 100%) 0 0 / 200% 100%;
  animation: brillo 1.4s ease-in-out infinite;
}
.marcador.alto {
  height: 72px;
  width: 60%;
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
  white-space: nowrap;
}
/* En una columna, lo que se usa para actuar va primero: importe, acciones, datos y comprobantes;
   la conversación antes que la historia. */
@media (max-width: 900px) {
  .rejilla {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 20px;
  }
  .principal,
  .lateral {
    display: contents;
  }
  .orden-1 {
    order: 1;
  }
  .orden-2 {
    order: 2;
  }
  .orden-3 {
    order: 3;
  }
  .orden-4 {
    order: 4;
  }
  .orden-5 {
    order: 5;
  }
  .orden-6 {
    order: 6;
  }
  .orden-7 {
    order: 7;
  }
}
@media (max-width: 600px) {
  .cabecera {
    grid-template-columns: 48px minmax(0, 1fr);
  }
  .icono {
    width: 48px;
    height: 48px;
  }
  .estado {
    grid-column: 1 / -1;
    justify-self: start;
  }
  .acciones :deep(.p-button) {
    flex: 1 1 100%;
  }
}
</style>
